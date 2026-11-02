"""Watch folder (PLAN.md Phase 7, user's choices 2026-10-25): ~/Lectures/inbox/<course-id>/.

The user moves downloaded recordings into the course's folder; the slide decks of the course live there too
(a "shelf": lecturers hand out one file per lecture in some courses, a few big decks for the whole semester
in others). The worker queues a recording once it has stopped changing for STABLE_S, with slides chosen by
pick_slides():
  1. a deck with the same file name, or with the same lecture number ("les 4", "lecture 4", "HC 4", "week 4")
     → only those;
  2. else, when the recording has a number and the shelf holds numbered decks (one file per lecture) → wait:
     the slides of this lecture aren't there yet (the Add page lists it, so the user can add it by hand);
  3. else every deck on the shelf: the slide ↔ transcript alignment picks the slides that were shown.
     An empty shelf waits EMPTY_SHELF_WAIT_S first, so slides moved in just after the video are still used.
Recordings stay where they are (the job keeps their path); a recording already in a job or the queue is skipped.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

from . import config as cfgmod
from .config import Config, Course
from .naming import SLIDE_EXT, VIDEO_EXT, guess_date, guess_title
from .util import read_json

STABLE_S = 30.0             # a download still growing has a fresh mtime
EMPTY_SHELF_WAIT_S = 600.0  # no slides in the course folder: give the user 10 min to move them in
RESERVED = {"uploads"}      # inbox/uploads holds browser uploads (Add page), not a course
_NUMBER = re.compile(r"(?<![a-z])(?:les|lecture|college|hoorcollege|hc|week)[\s_-]*0*(\d{1,2})(?!\d)", re.I)
_tick = threading.Lock()


def lecture_number(stem: str) -> int | None:
    """'DEP les 4 - Aula …' → 4, 'HC03_slides' → 3, 'Slides202627_Part2' → None."""
    m = _NUMBER.search(stem)
    return int(m.group(1)) if m else None


def pick_slides(video: Path, decks: list[Path]) -> tuple[list[Path] | None, str]:
    """(slides, why) or (None, why it waits)."""
    same = [d for d in decks if d.stem.lower() == video.stem.lower()]
    if same:
        return same, "same name"
    n = lecture_number(video.stem)
    numbers = {d: lecture_number(d.stem) for d in decks}
    if n is not None and (hits := sorted(d for d, k in numbers.items() if k == n)):
        return hits, f"lecture {n}"
    if n is not None and any(k is not None for k in numbers.values()):
        return None, f"waiting for the slides of lecture {n}"
    # No number on the recording: waiting wouldn't change that, so the alignment decides.
    return sorted(decks), "all decks of the course" if decks else "no slides"


def known_media(conf: Config) -> set[str]:
    """Recordings already in a job or in the queue (resolved paths)."""
    from .queue import Queue

    known = set()
    if conf.paths.jobs_dir.exists():
        for mf in conf.paths.jobs_dir.glob("*/manifest.json"):
            if media := read_json(mf).get("input", {}).get("media"):
                known.add(str(Path(media).resolve()))
    known |= {str(Path(i["media"]).resolve()) for i in Queue().snapshot()["items"]}
    return known


def ensure_folders(conf: Config, courses: list[Course]) -> None:
    """A folder per course that isn't archived (never removes any)."""
    from .semesters import course_semester, is_archived

    dates: dict[str, list[str]] = {}
    if conf.paths.jobs_dir.exists():
        for mf in conf.paths.jobs_dir.glob("*/manifest.json"):
            m = read_json(mf)
            dates.setdefault(m.get("course"), []).append(m.get("date") or "")
    for c in courses:
        if c.id not in RESERVED and not is_archived(c, course_semester(c, dates.get(c.id, []))):
            (conf.paths.inbox_dir / c.id).mkdir(parents=True, exist_ok=True)


def course_folders(conf: Config, courses: list[Course]) -> list[tuple[Path, str]]:
    """(folder, course id): the inbox by course id, and SwiftSkip's Downloads folders by course code."""
    ids = {c.id for c in courses}
    codes = {code.upper(): c.id for c in courses for code in c.codes}
    found = []
    for root, course_of in ((conf.paths.inbox_dir, lambda name: name if name in ids else None),
                            (conf.paths.downloads_inbox, lambda name: codes.get(name.upper()))):
        for folder in sorted(root.iterdir()) if root.is_dir() else []:
            if folder.is_dir() and course_of(folder.name):
                found.append((folder, course_of(folder.name)))
    return found


def scan(conf: Config, courses: list[Course], now: float | None = None) -> list[dict]:
    """New recordings in the course folders: {media, course, title, date, slides, why, ready}."""
    now = time.time() if now is None else now
    known = known_media(conf)
    out = []
    for folder, course_id in course_folders(conf, courses):
        files = [p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")]
        decks = [p for p in files if p.suffix.lower() in SLIDE_EXT]
        for video in sorted(p for p in files if p.suffix.lower() in VIDEO_EXT):
            if str(video.resolve()) in known:
                continue
            st = video.stat()
            slides, why = pick_slides(video, decks)
            ready = slides is not None and st.st_size > 0 and now - st.st_mtime >= STABLE_S
            if ready and not slides and now - st.st_mtime < EMPTY_SHELF_WAIT_S:
                ready, why = False, "no slides in the course folder yet (waits 10 min)"
            elif slides is not None and not ready:
                why = "still being copied or downloaded"
            out.append({"media": str(video), "course": course_id, "title": guess_title(video.stem),
                        "date": guess_date(video.stem, st.st_mtime), "slides": [str(s) for s in slides or []],
                        "why": why, "ready": ready})
    return out


def tick(queue, conf: Config, rep=None) -> list[dict]:
    """Queue what's ready (worker, every idle round). One caller at a time: the worker may run several loops."""
    if not _tick.acquire(blocking=False):
        return []
    try:
        courses = cfgmod.load_courses()
        ensure_folders(conf, courses)
        added = []
        for found in scan(conf, courses):
            if found["ready"]:
                added.append(queue.add(Path(found["media"]), found["course"], [Path(s) for s in found["slides"]],
                                       found["title"], found["date"], notes="never"))
                if rep:
                    rep(f"inbox: queued {found['title']} ({found['course']}, slides: {found['why']})")
        return added
    finally:
        _tick.release()
