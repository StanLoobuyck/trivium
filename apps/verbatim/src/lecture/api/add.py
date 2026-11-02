"""Add page: recordings found on this laptop (/api/suggestions), uploads, and adding lectures to the queue."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from .. import config as cfgmod
from ..naming import SLIDE_EXT, VIDEO_EXT, guess_course, guess_date, guess_title
from ..queue import NOTES_POLICIES
from ..util import file_fingerprint, read_json
from . import common
from .common import jobs_dir

router = APIRouter()


class NewItem(BaseModel):
    media: str
    course: str
    slides: list[str] = []
    title: str | None = None
    date: str | None = None
    notes: str = "never"  # app notes are optional (2026-10-20): the latex-notes skill only needs transcript + parts
    language: str | None = None  # spoken language; None = the course's


def upload_problem(path: Path) -> str | None:
    """Why an uploaded file can't be used, or None. Catches empty and half-downloaded recordings here,
    instead of as an ffprobe error in the queue minutes later."""
    if path.stat().st_size == 0:
        return "the file is empty (still downloading?)"
    if path.suffix.lower() in VIDEO_EXT:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(path)], capture_output=True, text=True, timeout=60)
        if out.returncode != 0 or not out.stdout.strip():
            return "can't read this recording (incomplete download or not a video/audio file)"
    return None


def _walk(root: Path, depth: int):
    try:
        for p in root.iterdir():
            if p.name.startswith("."):
                continue
            if p.is_file():
                yield p
            elif p.is_dir() and depth > 0:
                yield from _walk(p, depth - 1)
    except PermissionError:
        return


@router.get("/api/suggestions")
def suggestions():
    """Recent recordings not processed yet, and recent slide files (those used before for a course first)."""
    known_media, used_slides = set(), {}
    for mf in jobs_dir().glob("*/manifest.json"):
        m = read_json(mf)
        known_media.add(m.get("input", {}).get("media"))
        for s in m.get("slides", []):
            used_slides.setdefault(s["source"], m.get("course"))
    known_media |= {i["media"] for i in common.Queue().snapshot()["items"]}
    all_courses = cfgmod.load_courses()
    home = Path.home()
    videos = []
    for root in (home / "Videos" / "Recordings", home / "Videos", home / "Downloads",
                 cfgmod.load_config().paths.inbox_dir):
        if root.is_dir():
            for p in root.iterdir():
                if p.is_file() and p.suffix.lower() in VIDEO_EXT and str(p) not in known_media:
                    st = p.stat()
                    videos.append({"path": str(p), "name": p.name, "size": st.st_size, "mtime": st.st_mtime,
                                   "title": guess_title(p.stem), "date": guess_date(p.stem, st.st_mtime),
                                   "course": guess_course(p.stem, all_courses)})
    inbox = cfgmod.load_config().paths.inbox_dir  # course folders of the watch folder: the course is known
    ids = {c.id for c in all_courses}
    for folder in (d for d in inbox.iterdir() if d.is_dir() and d.name in ids) if inbox.is_dir() else []:
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in VIDEO_EXT and str(p) not in known_media:
                st = p.stat()
                videos.append({"path": str(p), "name": p.name, "size": st.st_size, "mtime": st.st_mtime,
                               "title": guess_title(p.stem), "date": guess_date(p.stem, st.st_mtime),
                               "course": folder.name})
    videos = sorted({v["path"]: v for v in videos}.values(), key=lambda v: -v["mtime"])[:20]
    slides = {}
    for root, depth in ((home / "Documents", 3), (home / "Downloads", 1), (inbox, 1)):
        if root.is_dir():
            for p in _walk(root, depth):
                if p.suffix.lower() in SLIDE_EXT:
                    shelf = p.parent.name if p.parent.parent == inbox and p.parent.name in ids else None
                    slides[str(p)] = {"path": str(p), "name": p.name, "mtime": p.stat().st_mtime,
                                      "course": shelf or used_slides.get(str(p))}
    # one entry per file name (the same deck often sits in Documents and Downloads): prefer the one used before
    by_name: dict[str, dict] = {}
    for sl in sorted(slides.values(), key=lambda s: (s["course"] is None, -s["mtime"])):
        by_name.setdefault(sl["name"].lower(), sl)
    slide_list = list(by_name.values())[:80]
    return {"videos": videos, "slides": slide_list}


@router.post("/api/upload")
async def upload(file: UploadFile):
    dest_dir = cfgmod.load_config().paths.inbox_dir / "uploads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload").name
    if Path(name).suffix.lower() not in VIDEO_EXT | SLIDE_EXT:
        raise HTTPException(400, "only video/audio, PDF or PPTX files")
    dest = dest_dir / name
    n = 1
    while dest.exists():
        dest = dest_dir / f"{Path(name).stem}-{n}{Path(name).suffix}"
        n += 1
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh, length=4 * 2**20)
    problem = upload_problem(dest)
    if problem:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, problem)
    # the same file dropped twice: keep the first copy instead of a "-1" duplicate
    size, fp = dest.stat().st_size, file_fingerprint(dest)
    for other in dest_dir.iterdir():
        if (other != dest and other.is_file() and other.stat().st_size == size
                and file_fingerprint(other) == fp):
            dest.unlink()
            dest = other
            break
    st = dest.stat()
    return {"path": str(dest), "name": dest.name, "size": st.st_size,
            "title": guess_title(dest.stem), "date": guess_date(dest.stem, st.st_mtime),
            "course": guess_course(dest.stem, cfgmod.load_courses())}


@router.post("/api/queue")
def add(items: list[NewItem]):
    known = {c.id for c in cfgmod.load_courses()}
    problems = []
    for it in items:
        if it.course not in known:
            problems.append(f"{Path(it.media).name}: choose a course")
        if it.notes not in NOTES_POLICIES:
            problems.append(f"{Path(it.media).name}: bad notes policy")
        for p in [it.media, *it.slides]:
            if not Path(p).is_file():
                problems.append(f"not found: {p}")
        if it.language not in (None, "nl", "en"):
            problems.append(f"{Path(it.media).name}: language must be nl or en")
        if it.date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", it.date):
            problems.append(f"{Path(it.media).name}: date must be YYYY-MM-DD")
    if problems:
        raise HTTPException(400, "; ".join(problems))
    q = common.Queue()
    from .. import inbox
    for it in items:  # added by hand: a recording stopped earlier may come back
        inbox.unignore(cfgmod.load_config(), Path(it.media))
    added = [q.add(Path(it.media), it.course, [Path(s) for s in it.slides], it.title or None, it.date or None,
                   it.notes, it.language) for it in items]
    return {"added": added, "worker": common.worker_running()}
