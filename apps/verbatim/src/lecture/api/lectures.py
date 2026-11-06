"""/api/lectures: the library, one lecture (transcript, notes, media, files), renames, word fixes and
term fix suggestions."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import config as cfgmod
from .. import library
from ..naming import guess_title
from ..util import read_json, write_json
from . import common
from .common import archive_status, job_dir, jobs_dir, lecture_summary, queue_by_job

router = APIRouter()


class Rename(BaseModel):
    title: str


@router.get("/api/lectures")
def lectures():
    queued = queue_by_job()
    courses = {c.id: c for c in cfgmod.load_courses()}
    lessons = common.library_lessons()
    out = [lecture_summary(mf.parent, queued, courses, lessons=lessons) for mf in jobs_dir().glob("*/manifest.json")]
    # lectures still waiting in the queue have no job folder yet
    jobs = {o["id"] for o in out}
    for i in common.Queue().snapshot()["items"]:
        if not i.get("job") or Path(i["job"]).name not in jobs:
            course = courses.get(i["course"])
            out.append({"id": None, "title": i.get("title") or guess_title(Path(i["media"]).stem),
                        "date": i.get("date"), "course": i["course"],
                        "course_name": course.name if course else i["course"], "status": i["status"],
                        "duration_s": None, "sections": None, "has_notes": False, "has_slides": bool(i["slides"]),
                        "queue": i})
    library.arrange([o for o in out if o["id"]])
    return sorted(out, key=lambda o: (o["date"] or "", o["title"]), reverse=True)


@router.get("/api/lectures/{name}")
def lecture(name: str):
    from ..stages.s7_notes import load_notes

    d = job_dir(name)
    queued = queue_by_job()
    courses = {c.id: c for c in cfgmod.load_courses()}
    summary = lecture_summary(d, queued, courses)
    tr = read_json(d / "transcript_raw.json") if (d / "transcript_raw.json").exists() else None
    sections = read_json(d / "sections.json") if (d / "sections.json").exists() else None
    notes = load_notes(d / "notes")
    outputs = d / "outputs"
    review = (outputs / "review.md").read_text(encoding="utf-8") if (outputs / "review.md").exists() else ""
    files = sorted(p.name for p in outputs.iterdir() if p.is_file()) if outputs.exists() else []
    media = read_json(d / "manifest.json").get("input", {}).get("media")
    terms = read_json(d / "terms.json") if (d / "terms.json").exists() else {}
    tf = read_json(d / "termfix.json") if (d / "termfix.json").exists() else None
    return {**summary,
            "termfix": {k: tf.get(k) for k in ("status", "error", "model", "made", "suggestions")} if tf else None,
            "terms": [{"term": x["term"], "source": x.get("source"), "slides": x.get("slides")}
                      for x in terms.get("terms", [])],
            "whisper_prompt": terms.get("whisper_prompt", ""),
            "fixes": tr.get("fixes", []) if tr else [],
            "corrections": courses[summary["course"]].corrections if summary["course"] in courses else {},
            "segments": [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in tr["segments"]]
            if tr else [],
            "sections_detail": sections["sections"] if sections else [],
            "slides_not_discussed": sections.get("slides_not_discussed", []) if sections else [],
            "notes": notes.model_dump() if notes else None, "review": review, "files": files,
            "latex_pdf": bool(_latex_pdf(d)), "can_latex": (d / "sections.json").exists(),
            "media_available": bool(media and Path(media).is_file()),
            "media_on_mac": archive_status(d)["on_mac"],
            "media_name": Path(media).name if media else None,
            "subtitles": (outputs / "subtitles.vtt").is_file(),
            "language": read_json(d / "manifest.json").get("language")}


def _latex_pdf(d: Path) -> Path | None:
    """The course document, once this lecture is in it."""
    from .. import latex

    manifest = read_json(d / "manifest.json")
    folder = latex.course_folder(cfgmod.load_config(), manifest.get("course", ""))
    written = folder / "lessen" / f"{latex.lecture_file(manifest)}.tex"
    pdf = folder / "main.pdf"
    return pdf if pdf.is_file() and written.is_file() else None


@router.post("/api/lectures/{name}/latex")
def make_latex(name: str):
    d = job_dir(name)
    if not (d / "sections.json").exists():
        raise HTTPException(409, "the transcript isn't ready yet")
    manifest = read_json(d / "manifest.json")
    item = common.Queue().add_latex(d, manifest.get("input", {}).get("media", ""), manifest.get("course", ""))
    return {"id": item["id"], "worker": common.worker_running()}


@router.get("/api/lectures/{name}/latex.pdf")
def latex_pdf(name: str):
    path = _latex_pdf(job_dir(name))
    if not path:
        raise HTTPException(404, "no LaTeX notes yet")
    return FileResponse(path, media_type="application/pdf")


@router.get("/api/lectures/{name}/media")
def media(name: str):
    d = job_dir(name)
    path = read_json(d / "manifest.json").get("input", {}).get("media")
    if not path or not Path(path).is_file():
        raise HTTPException(404, "original recording not found")
    from ..player import ensure_player

    # lectures from before the player stage get their copy on first view (a few seconds)
    player = ensure_player(d, Path(path))
    return FileResponse(player or path)  # supports Range requests: the player can seek


@router.get("/api/lectures/{name}/subtitles.vtt")
def subtitles(name: str):
    # its own route for the <track>: Firefox only shows WebVTT served as text/vtt, and "files/" sends attachments
    path = job_dir(name) / "outputs" / "subtitles.vtt"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="text/vtt; charset=utf-8", headers={"Cache-Control": "no-cache"})


@router.get("/api/lectures/{name}/files/{file}")
def download(name: str, file: str):
    path = job_dir(name) / "outputs" / file
    if not re.fullmatch(r"[\w.-]+", file) or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, filename=file)


@router.post("/api/lectures/{name}/open-folder")
def open_folder(name: str):
    d = job_dir(name)
    # A lecture still running has no outputs yet: show its folder rather than nothing.
    target = d / "outputs" if (d / "outputs").is_dir() else d
    subprocess.Popen(["xdg-open", str(target)], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    return {"ok": True}


@router.delete("/api/lectures/{name}")
def delete_lecture(name: str):
    from .. import settings

    d = job_dir(name)
    try:
        common.Queue().forget_job(d)
    except KeyError as exc:
        raise HTTPException(409, str(exc).strip("'")) from None
    media = read_json(d / "manifest.json").get("input", {}).get("media")
    shutil.rmtree(d)
    # the app's own upload copy goes too, unless another lecture uses it; recordings elsewhere stay
    uploads = cfgmod.load_config().paths.inbox_dir / "uploads"
    if media and Path(media).parent == uploads and not any(
            read_json(mf).get("input", {}).get("media") == media for mf in jobs_dir().glob("*/manifest.json")):
        Path(media).unlink(missing_ok=True)
    f = settings.folders()
    if f["assign"].pop(name, None):
        settings.save_folders(f)
    return {"ok": True}


@router.post("/api/lectures/{name}/rename")
def rename_lecture(name: str, body: Rename):
    d = job_dir(name)
    title = " ".join(body.title.split())[:120]
    if not title:
        raise HTTPException(400, "the title is empty")
    try:
        common.Queue().retitle(d, title)
    except KeyError as exc:
        raise HTTPException(409, str(exc).strip("'")) from None
    m = read_json(d / "manifest.json")
    m["title"] = title
    write_json(d / "manifest.json", m)
    return {"title": title}


@router.post("/api/lectures/{name}/refix")
def refix(name: str):
    """Re-apply the course fix list now (stitch → review; a few seconds, no speech-to-text, no LLM)."""
    from ..job import Job, JobLockedError
    from ..pipeline import refix as run_refix
    from ..report import NullReporter

    d = job_dir(name)
    if read_json(d / "manifest.json").get("stages", {}).get("stitch", {}).get("status") != "done":
        raise HTTPException(409, "the lecture isn't transcribed yet")
    try:
        run_refix(Job(d), cfgmod.load_config(), NullReporter())
    except JobLockedError:
        raise HTTPException(409, "the worker is busy with this lecture; try again in a minute") from None
    return {"fixes": read_json(d / "transcript_raw.json").get("fixes", [])}


@router.post("/api/lectures/{name}/termfix/run")
def termfix_run(name: str):
    """(Re)make the term fix suggestions on the Mac, in a background thread (minutes; the UI polls)."""
    import threading

    from .. import termfix
    from ..job import Job
    from ..pipeline import run_termfix
    from ..report import NullReporter

    d = job_dir(name)
    if not (d / "transcript_raw.json").exists():
        raise HTTPException(409, "the lecture isn't transcribed yet")
    job = Job(d)
    old = termfix.load(job)
    if old and old.get("status") == "running":
        raise HTTPException(409, "suggestions are being made already")
    fresh = bool(old and old.get("status") == "done")  # "make them again": ask anew; else resume / first time
    termfix.mark(job, "running", "")

    def work():
        try:
            run_termfix(job, cfgmod.load_config(), NullReporter(), fresh=fresh)
        except Exception:  # noqa: BLE001 — recorded in termfix.json by run_termfix
            pass

    threading.Thread(target=work, daemon=True, name=f"termfix-{name}").start()
    return {"status": "running"}


@router.post("/api/lectures/{name}/termfix/{sid}")
def termfix_set(name: str, sid: str, body: dict = Body(...)):
    """Accept / reject / reopen one suggestion, or add it to the course fix list ("course");
    re-stitches at once when what's applied changes (a few seconds, no speech-to-text, no LLM)."""
    from .. import settings, termfix
    from ..job import Job, JobLockedError
    from ..pipeline import refix as run_refix
    from ..report import NullReporter

    d = job_dir(name)
    job = Job(d)
    status = body.get("status")
    try:
        before = next(s for s in (termfix.load(job) or {}).get("suggestions", []) if s["id"] == sid)
        sug = termfix.set_status(job, sid, status)
    except StopIteration:
        raise HTTPException(404, f"no suggestion {sid}") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    changed = "accepted" in (before["status"], status)
    if status == "course" or before["status"] == "course":
        course = {c.id: c for c in cfgmod.load_courses()}[job.manifest["course"]].model_dump()
        if status == "course":
            course["corrections"][sug["wrong"]] = sug["right"]
        elif course["corrections"].get(sug["wrong"]) == sug["right"]:
            del course["corrections"][sug["wrong"]]
        settings.save_course(course)
        changed = True
    if changed:
        try:
            run_refix(job, cfgmod.load_config(), NullReporter())
        except JobLockedError:
            termfix.set_status(job, sid, before["status"])
            raise HTTPException(409, "the worker is busy with this lecture; try again in a minute") from None
    return {"suggestion": sug, "fixes": read_json(d / "transcript_raw.json").get("fixes", [])}


@router.post("/api/lectures/{name}/notes")
def make_notes(name: str):
    d = job_dir(name)
    m = read_json(d / "manifest.json")
    if m.get("stages", {}).get("sections", {}).get("status") != "done":
        raise HTTPException(409, "the lecture isn't transcribed yet")
    item = common.Queue().add_notes(d, m["input"]["media"], m["course"])
    return {"item": item, "worker": common.worker_running()}
