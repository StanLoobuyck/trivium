"""Settings: /api/setup (models, keys, outputs), courses and library folders."""

from __future__ import annotations


import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config as cfgmod
from . import common
from .common import llm_label, mac_status, stt_label

router = APIRouter()


# request bodies live at module level: FastAPI can't resolve models defined inside create_app()
# when annotations are strings (from __future__ import annotations)
class Choice(BaseModel):
    value: str


class Outputs(BaseModel):
    exam_hints: bool | None = None
    quiz: bool | None = None
    flashcards: bool | None = None
    glossary: bool | None = None


class KeyIn(BaseModel):
    name: str
    value: str


class CourseIn(BaseModel):
    id: str | None = None
    name: str
    language: str = "nl"
    lecturer: str | None = None
    extra_terms: list[str] = []
    notes_language: str | None = None
    corrections: dict[str, str] = {}
    codes: list[str] = []
    # must be listed here: fields missing from this model were silently dropped on every save (2026-10-20)
    semester: str | None = None
    archived: bool | None = None
    notes_without_slides: bool = False


class Flag(BaseModel):
    value: bool


@router.get("/api/courses")
def courses():
    return [c.model_dump() for c in cfgmod.load_courses()]


def _version() -> str:
    from .. import updates

    return updates.current_version()


def _update_info():
    from .. import updates

    if updates.install_dir() is None:
        return None
    new = updates.cached()
    return {"current": updates.current_version(), "version": new["version"], "notes": new["notes"]} if new else None


@router.post("/api/update")
def update_now():
    """Windows app: install the newer version and quit (the installer reopens Verbatim)."""
    import os
    import threading

    from .. import updates

    if updates.install_dir() is None:
        raise HTTPException(400, "updates only apply to the Windows app")
    if updates.busy(common.Queue().snapshot()):
        raise HTTPException(409, "busy")
    new = updates.cached()
    if not new:
        raise HTTPException(404, "no newer version")
    try:
        updates.start(cfgmod.load_config(), new)
    except Exception as exc:  # noqa: BLE001 — offline, checksum, …: say why, keep running
        raise HTTPException(502, f"update failed: {exc}") from None
    threading.Timer(1.5, lambda: os._exit(0)).start()  # let this answer reach the page first
    return {"ok": True, "version": new["version"]}


@router.get("/api/setup")
def setup():
    """Everything the Setup panel and the dashboard's tool strip show. Cheap checks only, no paid calls."""
    from .. import settings
    from ..status import gpu, on_battery

    conf = cfgmod.load_config()
    keys = settings.key_status()
    claude = settings.claude_login()
    local_ok = settings.local_whisper_available()
    gpu_text = gpu()
    gpu_ok = local_ok and not gpu_text.lower().startswith(("gpu unusable", "nvidia-smi failed", "no nvidia"))
    mac_ok, mac_detail = mac_status(conf)

    plan = (claude.get("plan") or "").capitalize()

    from ..models import notes_status

    def notes_ok(entry: str) -> tuple[bool, str]:
        return notes_status(conf, entry, keys, claude)

    chain = conf.llm.tasks["notes"]
    choices = [{"value": c, "label": llm_label(c, conf), "ok": notes_ok(c)[0], "detail": notes_ok(c)[1]}
               for c in conf.llm.notes_choices]
    fallbacks = [{"value": c, "label": llm_label(c, conf), "ok": notes_ok(c)[0], "detail": notes_ok(c)[1]}
                 for c in chain[1:] if c.split(":")[0] in ("claude", "gemini", "custom")]
    mode = {"mac": "mac", "local": "local"}.get(conf.stt.providers[0], "cloud")
    from ..models import stt_status

    order = []
    for entry in conf.stt.providers:  # the chain: the first usable entry does the next lecture
        ok, detail = stt_status(conf, entry, gpu_ok, keys["groq"])
        order.append({"entry": entry, "label": stt_label(entry, conf), "ok": ok, "detail": detail,
                      "custom": entry.startswith("custom:")})
    first_ok = next((i for i, o in enumerate(order) if o["ok"]), None)
    active = order[first_ok]["entry"] if first_ok is not None else conf.stt.providers[-1]
    snap = common.Queue().snapshot()
    from ..models import termfix_status

    tf_ok, tf_detail = termfix_status(conf)
    return {
        "app_name": "Lecture Transcriber",
        "version": _version(),
        "simple": conf.app.simple,
        "welcomed": conf.app.welcomed,
        "auto_notes": conf.app.auto_notes,
        "update": _update_info(),
        "termfix": {"enabled": conf.termfix.enabled and not conf.app.simple, "model": conf.termfix.model, "ok": tf_ok, "detail": tf_detail},
        "stt": {"mode": mode, "local_available": local_ok, "gpu_ok": gpu_ok, "gpu": gpu_text,
                "local_label": stt_label("local", conf), "cloud_label": stt_label("groq", conf),
                "mac_label": stt_label("mac", conf), "mac_ok": mac_ok, "mac_detail": mac_detail,
                "groq_key": keys["groq"], "active_provider": active,
                "active": stt_label(active, conf), "active_ok": first_ok is not None,
                "fallback": bool(first_ok), "order": order,
                "skip_on_battery": conf.stt.local.skip_on_battery, "on_battery": on_battery()},
        "claude_plan": plan,
        "notes": {"choice": chain[0], "label": llm_label(chain[0], conf), "ok": notes_ok(chain[0])[0],
                  "detail": notes_ok(chain[0])[1], "choices": choices, "fallbacks": fallbacks},
        "outputs": conf.notes.outputs.model_dump(),
        "keys": keys,
        "mac": {"url": conf.stt.mac.url if conf.stt.mac else None, "token": keys["mac"]},
        "hub": {"url": conf.hub.url, "code": keys["hub"]},
        "worker": common.worker_running(),
        "notes_paused": snap["notes_paused"],
    }


def _apply(fn, *args):
    try:
        fn(*args)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc).strip("'")) from None
    except Exception as exc:  # noqa: BLE001 — a rejected change (rolled back) is the user's to fix
        raise HTTPException(400, f"not saved: {exc}") from None
    return {"ok": True}


@router.post("/api/setup/notes-model")
def set_notes_model(body: Choice):
    from .. import settings
    return _apply(settings.set_notes_model, body.value)


@router.post("/api/setup/stt")
def set_stt(body: Choice):
    from .. import settings
    return _apply(settings.set_stt_mode, body.value)


@router.post("/api/setup/auto-notes")
def set_auto_notes(body: Flag):
    from .. import settings
    return _apply(settings.update_settings, {"app": {"auto_notes": body.value}})


@router.post("/api/setup/stt-battery")
def set_stt_battery(body: Flag):
    from .. import settings
    return _apply(settings.set_skip_on_battery, body.value)


@router.post("/api/setup/outputs")
def set_outputs(body: Outputs):
    from .. import settings
    return _apply(settings.set_outputs, {k: v for k, v in body.model_dump().items() if v is not None})


@router.post("/api/setup/key")
def set_key(body: KeyIn):
    from .. import settings
    return _apply(settings.set_key, body.name, body.value)


@router.post("/api/setup/key/test")
def test_key(body: KeyIn):
    """Welcome steps: try the key with the service and save it when it works."""
    from .. import settings
    try:
        return settings.test_key(body.name, body.value)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/api/setup/welcome-done")
def welcome_done():
    from .. import settings
    return _apply(settings.finish_welcome)


@router.post("/api/courses")
def save_course(body: CourseIn):
    from .. import settings
    try:
        c = settings.save_course(body.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"not saved: {exc}") from None
    return {"id": c.id}


@router.delete("/api/courses/{course_id}")
def delete_course(course_id: str):
    from .. import settings
    return _apply(settings.delete_course, course_id)


@router.get("/api/folders")
def get_folders():
    from .. import settings
    return settings.folders()


@router.post("/api/folders")
def put_folders(body: dict):
    from .. import settings
    try:
        return settings.save_folders(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


class MacIn(BaseModel):
    url: str


@router.post("/api/setup/mac")
def set_mac(body: MacIn):
    from .. import models, settings

    _apply(settings.set_mac_url, body.url)
    models._mac_cache["at"] = -1e9  # next status check asks the new address
    return {"url": cfgmod.load_config().stt.mac.url}


@router.post("/api/setup/hub")
def set_hub(body: MacIn):
    from .. import settings

    _apply(settings.set_hub_url, body.url)
    return {"url": cfgmod.load_config().hub.url}


@router.post("/api/setup/hub/import")
def import_from_hub():
    from .. import hub, settings

    try:
        return settings.import_courses(hub.fetch_courses(cfgmod.load_config()))
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(400, f"hub: {exc}") from None


@router.get("/api/course-colors")
def course_colors():
    """Same colour per course as Sequo. Empty without a hub: the page then keeps what it last knew."""
    from .. import hub

    try:
        return hub.course_colors(cfgmod.load_config(), cfgmod.load_courses())
    except (ValueError, httpx.HTTPError):
        return {}


@router.post("/api/setup/mac/test")
def test_mac():
    from .. import models

    return models.test_mac(cfgmod.load_config())
