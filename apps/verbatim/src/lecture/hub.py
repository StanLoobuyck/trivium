"""The optional link with your own Inhaal hub (packages/contract/CONTRACT.md): courses in, "notes ready" out.

Verbatim works alone: without an address nothing here does anything. Which lectures Inhaal was told about is kept
next to the jobs; the worker compares that with the jobs every idle round. So older lectures are reported too, what
couldn't be delivered goes out later, and the settings are read fresh: a worker started before the link still sees it.
"""

from __future__ import annotations

import re
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


def course_colors(conf: Config, courses: list[Course]) -> dict[str, str]:
    """Inhaal's colour per Verbatim course id, matched like settings.import_courses: same code, else same name."""
    def key(name: str) -> str:
        return " ".join(name.lower().split())

    colors = {}
    for entry in fetch_courses(conf):
        wanted = {c.upper() for c in entry.get("codes") or []}
        same = next((c for c in courses if wanted & {x.upper() for x in c.codes}), None) \
            or next((c for c in courses if key(c.name) == key(entry.get("name") or "")), None)
        if same and entry.get("colorKey"):
            colors[same.id] = entry["colorKey"]
    return colors


_NAME_NOISE = re.compile(r"\(.*?\)|\b\d{4}-\d{2}-\d{2}\b.*")
_YEAR_AT_END = re.compile(r"[\s-]+\d{4}$")
_LAST_NUMBER = re.compile(r"[^\W\d]\s+0*(\d{1,2})\s*$")


def trailing_number(name: str) -> int | None:
    """'RZL Ingenieurswetenschappen 5 - 2026 (2026-10-19)' → 5. Dates, years and clock times don't count."""
    m = _LAST_NUMBER.search(_YEAR_AT_END.sub("", _NAME_NOISE.sub("", name).strip()))
    return int(m[1]) if m and int(m[1]) else None


def notes_event(job: dict, job_name: str, kind: str, course: Course) -> dict:
    title = job.get("title") or ""
    media = Path(job.get("input", {}).get("media", ""))
    date = job.get("date") or ""
    recording = {"courseCode": course.codes[0], "title": title,
                 # a date Verbatim only guessed from the file's age says nothing about the lecture
                 "recordedOn": date if date and date in media.stem else None,
                 "fileName": media.name or None,
                 "lectureNumber": (lecture_number(title) or lecture_number(media.stem)
                                    or trailing_number(title) or trailing_number(media.stem))}
    # The number is in the id: a lecture told again with a better number isn't dropped as a duplicate.
    return {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"verbatim/{job_name}/{kind}/{recording['lectureNumber']}")),
            "type": "notes.ready",
            "source": "verbatim", "occurredAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "payload": {"recording": {k: v for k, v in recording.items() if v}, "kind": kind,
                        "verbatimJob": job_name}}


def _ready(job_root: Path) -> list[str]:
    outputs = job_root / "outputs"
    return [kind for kind, name in (("transcript", "transcript.md"), ("notes", "notes.md"))
            if (outputs / name).exists()]


def report() -> int:
    """Tell the hub about every finished lecture it hasn't heard of. Returns how many messages went out."""
    conf = cfgmod.load_config()
    link = _auth(conf)
    if not link or not conf.paths.jobs_dir.is_dir():
        return 0
    path = conf.paths.jobs_dir / "hub_sent.json"
    sent = set(read_json(path) or []) if path.exists() else set()
    courses = {c.id: c for c in cfgmod.load_courses()}
    count = 0
    try:
        for manifest in sorted(conf.paths.jobs_dir.glob("*/manifest.json")):
            root = manifest.parent
            for kind in _ready(root):
                key = f"{root.name}/{kind}"
                if key in sent:
                    continue
                job = read_json(manifest)
                course = courses.get(job.get("course"))
                if not course or not course.codes:
                    continue
                httpx.post(f"{link[0]}/api/events", json=notes_event(job, root.name, kind, course), headers=link[1],
                           timeout=TIMEOUT_S).raise_for_status()
                sent.add(key)
                count += 1
    except httpx.HTTPError as exc:
        print(f"hub: {type(exc).__name__}: {exc}", flush=True)  # the next round tries again
    if count:
        write_json(path, sorted(sent))
    return count


def report_quietly() -> None:
    """Never fails a lecture or the worker: this is a courtesy to another app."""
    try:
        report()
    except Exception as exc:  # noqa: BLE001
        print(f"hub: {type(exc).__name__}: {exc}", flush=True)
