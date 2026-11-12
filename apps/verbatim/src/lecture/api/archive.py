"""/api/semesters and /api/archive: semesters, archived courses, media copies to the Mac and back.

Moving media takes a while (tens of MB/s at best over Tailscale), so it runs in one background thread at a
time; the page polls /api/archive/progress.
"""

from __future__ import annotations

import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import archive, semesters, settings
from .. import config as cfgmod
from ..util import read_json

router = APIRouter()
_progress: dict = {"running": False, "action": None, "label": "", "done": 0, "total": 0, "error": None,
                   "bytes": 0, "finished": None}
_lock = threading.Lock()


class ArchivedIn(BaseModel):
    archived: bool | None = None   # None = automatic again (by semester)


class MoveIn(BaseModel):
    semester: str | None = None
    jobs: list[str] = []


def _jobs() -> list[Path]:
    root = cfgmod.load_config().paths.jobs_dir
    return sorted(d for d in root.iterdir() if (d / "manifest.json").exists()) if root.exists() else []


def _lecture_rows() -> list[dict]:
    rows = []
    for d in _jobs():
        m = read_json(d / "manifest.json")
        st = archive.status(d)
        rows.append({"id": d.name, "title": m.get("title") or d.name, "course": m.get("course"), "date": m.get("date"),
                     "created": m.get("created"),
                     "duration_s": m.get("stages", {}).get("audio", {}).get("duration_s"),
                     "on_mac": st["on_mac"], "local_bytes": st["local_bytes"]})
    return rows


@router.get("/api/semesters")
def list_semesters():
    courses = cfgmod.load_courses()
    rows = _lecture_rows()
    ov = semesters.overview(courses, rows)
    names = {c.id: c.name for c in courses}
    out = []
    for sem, ids in ov["semesters"].items():
        lec = [r for r in rows if r["course"] in ids]
        out.append({"name": sem, "current": sem == ov["current"],
                    "archived": all(ov["courses"][i]["archived"] for i in ids),
                    "courses": [{"id": i, "name": names[i], "archived": ov["courses"][i]["archived"],
                                 "explicit": ov["courses"][i]["explicit"],
                                 "lectures": [r for r in lec if r["course"] == i]} for i in ids],
                    "local_bytes": sum(r["local_bytes"] for r in lec), "on_mac": sum(r["on_mac"] for r in lec)})
    return {"current": ov["current"], "courses": ov["courses"], "semesters": out,
            "remote": cfgmod.load_config().archive.remote}


@router.post("/api/courses/{course_id}/archived")
def set_archived(course_id: str, body: ArchivedIn):
    course = next((c for c in cfgmod.load_courses() if c.id == course_id), None)
    if course is None:
        raise HTTPException(404, "course not found")
    settings.save_course({**course.model_dump(), "archived": body.archived})
    return {"ok": True}


def _run(action: str, jobs: list[Path]) -> None:
    def progress(label, i, n):
        _progress.update(label=label)

    try:
        for i, d in enumerate(jobs):
            _progress.update(done=i, label=d.name)
            r = archive.move_to_remote(d, progress=progress) if action == "move" else archive.restore(d, progress=progress)
            _progress["bytes"] += r.get("bytes", 0)
        _progress.update(done=len(jobs))
    except Exception as exc:  # noqa: BLE001 — shown on the Archive page
        _progress["error"] = str(exc)
    finally:
        from datetime import datetime

        _progress.update(running=False, finished=datetime.now().isoformat(timespec="seconds"))


def _start(action: str, body: MoveIn) -> dict:
    jobs = {d.name: d for d in _jobs()}
    if body.jobs:
        chosen = [jobs[j] for j in body.jobs if j in jobs]
    elif body.semester:
        sem = next((s for s in list_semesters()["semesters"] if s["name"] == body.semester), None)
        if sem is None:
            raise HTTPException(404, "semester not found")
        chosen = [jobs[r["id"]] for c in sem["courses"] for r in c["lectures"]
                  if r["id"] in jobs and (r["local_bytes"] if action == "move" else r["on_mac"])]
    else:
        raise HTTPException(400, "give a semester or lectures")
    with _lock:
        if _progress["running"]:
            raise HTTPException(409, "already moving files; wait until it's done")
        _progress.update(running=True, action=action, label="", done=0, total=len(chosen), error=None, bytes=0,
                         finished=None)
    threading.Thread(target=_run, args=(action, chosen), daemon=True).start()
    return {"started": len(chosen)}


@router.post("/api/archive/move")
def move(body: MoveIn):
    return _start("move", body)


@router.post("/api/archive/restore")
def restore(body: MoveIn):
    return _start("restore", body)


@router.get("/api/archive/progress")
def progress():
    return _progress
