"""Helpers shared by the web API routers: job folders, the queue, model labels, a lecture's summary row.

Queue and worker_running are looked up here at call time (common.Queue()), so tests replace them in one place.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .. import config as cfgmod
from ..queue import Queue, worker_running  # noqa: F401 — re-exported for the routers
from ..util import read_json


def jobs_dir() -> Path:
    return cfgmod.load_config().paths.jobs_dir


def job_dir(name: str) -> Path:
    if not re.fullmatch(r"[\w.-]+", name):
        raise HTTPException(404)
    d = jobs_dir() / name
    if not (d / "manifest.json").exists():
        raise HTTPException(404, "unknown lecture")
    return d


def queue_by_job() -> dict[str, dict]:
    return {i["job"]: i for i in Queue().snapshot()["items"] if i.get("job")}


def llm_label(entry: str, conf=None) -> str:
    """'claude:claude-sonnet-5-5' → 'Claude Sonnet 5.5'; 'gemini:gemini-3.8-flash' → 'Gemini 3.8 Flash';
    'custom:<id>' → the name the user gave the model in Settings."""
    provider, _, model = entry.partition(":")
    if provider == "custom" and conf is not None:
        try:
            m = conf.model_entry(entry)
            return m.label or m.model
        except StopIteration:
            return model
    name = model.split("/")[-1]
    m = re.fullmatch(r"claude-(\w+)-(\d+)-(\d+)", name)
    if m:
        return f"Claude {m.group(1).capitalize()} {m.group(2)}.{m.group(3)}"
    if provider == "gemini":
        return " ".join(w.capitalize() if not w[0].isdigit() else w for w in name.split("-"))
    if provider == "groq":
        return f"{name.upper()} (Groq)"
    return name


def mac_status(conf) -> tuple[bool, str]:
    """(usable, detail) of the Mac's default model (see models.stt_status)."""
    from ..models import stt_status

    return stt_status(conf, "mac", False, False)


def stt_label(provider: str | None, conf) -> str:
    if provider and provider.startswith("custom:"):
        try:
            m = conf.model_entry(provider)
        except StopIteration:
            return provider
        return m.label or (f"Whisper {m.model} · Mac at home" if m.provider == "mac" else f"{m.model} · Groq cloud")
    if provider == "mac":
        return f"Whisper {conf.stt.mac.model if conf.stt.mac else '?'} · Mac at home"
    if provider == "local":  # GPU or processor (device auto): "this laptop" is true either way
        return f"Whisper {conf.stt.local.model} · {'your GPU' if conf.stt.local.device == 'cuda' else 'this laptop'}"
    return f"Whisper {conf.stt.model.removeprefix('whisper-')} · Groq cloud"


def models_used(d: Path, m: dict, conf, item: dict | None) -> dict[str, Any]:
    """Which model did / does each step: speech-to-text (from the run) and notes (from the saved batches)."""
    run = m.get("stt", {}).get("current_run")
    stt_provider = m.get("stt", {}).get("runs", {}).get(run, {}).get("provider") if run else None
    notes_models = []
    for b in sorted((d / "notes").glob("batch_*.json")) if (d / "notes").exists() else []:
        rec = read_json(b)
        notes_models.append(llm_label(f"{rec.get('provider', '').split(':')[0]}:{rec.get('model', '')}"))
    return {"stt": stt_label(stt_provider, conf) if stt_provider or run else None,
            "notes": ", ".join(dict.fromkeys(notes_models)) or None}


def step_model(item: dict, conf) -> str | None:
    """The model the running step of a queue item uses right now."""
    if item["status"] == "transcribing" and item.get("stage") == "transcribe":
        if item.get("job") and (Path(item["job"]) / "manifest.json").exists():
            m = read_json(Path(item["job"]) / "manifest.json")
            run = m.get("stt", {}).get("current_run")
            prov = m.get("stt", {}).get("runs", {}).get(run, {}).get("provider") if run else None
            if prov:
                return stt_label(prov, conf)
        return stt_label(conf.stt.providers[0], conf)
    if item["status"] == "notes" and conf.llm.tasks["notes"]:
        return llm_label(conf.llm.tasks["notes"][0], conf)
    return None


def archive_status(d: Path) -> dict[str, Any]:
    from ..archive import status

    return status(d)


def library_lessons() -> dict[str, list[dict]]:
    """Lesson numbers per course from the hub (cached, refreshed in the background); {} without a hub."""
    from .. import hub, library

    def refresh():
        courses = cfgmod.load_courses()
        return library.lessons_from_hub(hub.fetch_courses(cfgmod.load_config()), courses)
    return library.cached_lessons(jobs_dir() / "hub_lessons.json", refresh)


def lecture_summary(d: Path, queued: dict[str, dict], courses: dict, conf=None, lessons=None) -> dict[str, Any]:
    from ..library import display_title

    m = read_json(d / "manifest.json")
    st = m.get("stages", {})
    item = queued.get(str(d))
    has_notes = (d / "notes").exists() and any((d / "notes").glob("batch_*.json"))
    if item and item["status"] in ("queued", "transcribing", "notes", "notes_pending", "failed", "transcribed"):
        status = item["status"]
    elif has_notes:
        status = "done"
    elif st.get("sections", {}).get("status") == "done":
        status = "transcribed"
    else:
        status = m.get("status", "queued")
    course = courses.get(m.get("course"))
    sections = st.get("sections", {}).get("sections")
    media = (m.get("input") or {}).get("media")
    lessons = library_lessons() if lessons is None else lessons
    title = display_title(m.get("title") or d.name, Path(media).stem if media else None, m.get("date"),
                          lessons.get(m.get("course"), []), course.language if course else "nl")
    return {"id": d.name, "title": title, "date": m.get("date"), "created": m.get("created"), "course": m.get("course"),
            "course_name": course.name if course else m.get("course"), "status": status,
            "duration_s": st.get("audio", {}).get("duration_s"), "sections": sections, "has_notes": has_notes,
            "has_slides": bool(m.get("slides")), "queue": item,
            "models": models_used(d, m, conf or cfgmod.load_config(), item),
            "step_model": step_model(item, conf or cfgmod.load_config()) if item else None}
