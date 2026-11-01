"""The optional link with your own Inhaal hub (packages/contract/CONTRACT.md): courses in, "notes ready" out.

Verbatim works alone: without an address nothing here does anything. A message that can't be delivered waits in
an outbox next to the jobs; the worker retries it, and the hub ignores doubles.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import httpx

from . import config as cfgmod
from .config import Config, Course
from .inbox import lecture_number
from .util import read_json, write_json

TIMEOUT_S = 10.0


def _auth(conf: Config) -> tuple[str, dict] | None:
    code = cfgmod.load_keys()["LECTURE_HUB_CODE"]
    return (conf.hub.url.rstrip("/"), {"Authorization": f"Bearer {code}"}) if conf.hub.url and code else None


def fetch_courses(conf: Config) -> list[dict]:
    link = _auth(conf)
    if not link:
        raise ValueError("fill in the hub address and pairing code first")
    response = httpx.get(f"{link[0]}/api/courses", headers=link[1], timeout=TIMEOUT_S)
    response.raise_for_status()
    return response.json()["courses"]


def notes_event(job: dict, job_name: str, kind: str, course: Course) -> dict:
    title = job.get("title") or ""
    recording = {"courseCode": course.codes[0], "title": title, "recordedOn": job.get("date"),
                 "fileName": Path(job.get("input", {}).get("media", "")).name or None,
                 "lectureNumber": lecture_number(title)}
    return {"id": str(uuid.uuid4()), "type": "notes.ready", "source": "verbatim",
            "occurredAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "payload": {"recording": {k: v for k, v in recording.items() if v}, "kind": kind,
                        "verbatimJob": job_name}}


def _outbox(conf: Config) -> Path:
    return conf.paths.jobs_dir / "hub_outbox.json"


def flush(conf: Config) -> None:
    """Send what waits; what fails stays for the next round."""
    path, link = _outbox(conf), _auth(conf)
    if not link or not path.exists():
        return
    waiting = read_json(path) or []
    left = list(waiting)
    for event in waiting:
        try:
            httpx.post(f"{link[0]}/api/events", json=event, headers=link[1], timeout=TIMEOUT_S).raise_for_status()
        except httpx.HTTPError:
            break
        left.remove(event)
    write_json(path, left)


def flush_quietly(conf: Config) -> None:
    try:
        flush(conf)
    except Exception as exc:  # noqa: BLE001 — must not stop the worker
        print(f"hub: {type(exc).__name__}: {exc}", flush=True)


def tell_notes_ready(job_root: Path, kind: str, conf: Config) -> None:
    """Never fails a lecture: this is a courtesy to another app."""
    try:
        if not _auth(conf):
            return
        job = read_json(job_root / "manifest.json")
        course = next((c for c in cfgmod.load_courses() if c.id == job.get("course")), None)
        if not course or not course.codes:
            return
        path = _outbox(conf)
        write_json(path, [*((read_json(path) or []) if path.exists() else []),
                          notes_event(job, job_root.name, kind, course)])
        flush(conf)
    except Exception as exc:  # noqa: BLE001
        print(f"hub: {type(exc).__name__}: {exc}", flush=True)
