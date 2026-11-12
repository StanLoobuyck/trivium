"""/api/models: models the user adds in Settings, the speech-to-text order, and the Test button."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config as cfgmod
from .. import models

router = APIRouter(prefix="/api/models")


class ModelIn(BaseModel):
    kind: Literal["stt", "notes"]
    preset: str
    model: str
    label: str = ""
    base_url: str | None = None
    key_name: str | None = None
    key: str | None = None  # the API key pasted in the form (never sent back)


class OrderIn(BaseModel):
    order: list[str]


class TestIn(BaseModel):
    kind: Literal["stt", "notes"]
    entry: str


def _apply(fn, *args):
    try:
        return fn(*args)
    except (ValueError, KeyError, StopIteration) as exc:
        raise HTTPException(400, str(exc).strip("'") or "not found") from None
    except Exception as exc:  # noqa: BLE001 — a rejected change (rolled back) is the user's to fix
        raise HTTPException(400, f"not saved: {exc}") from None


@router.get("")
def list_models():
    conf = cfgmod.load_config()
    return {"models": [m.model_dump() for m in conf.models],
            "presets": {"stt": list(models.STT_PRESETS), "notes": list(models.NOTES_PRESETS)}}


@router.post("")
def add_model(body: ModelIn):
    return {"id": _apply(models.add_model, body.kind, body.preset, body.model, body.label, body.base_url, body.key_name,
                       body.key)}


@router.delete("/{model_id}")
def remove_model(model_id: str):
    _apply(models.remove_model, model_id)
    return {"ok": True}


class NotesIn(BaseModel):
    entry: str


@router.post("/notes/remove")
def remove_notes(body: NotesIn):
    """Any notes model, also the built-in ones; one the user added goes completely."""
    _apply(models.remove_notes_choice, body.entry)
    return {"ok": True}


@router.post("/order")
def set_order(body: OrderIn):
    _apply(models.set_stt_order, body.order)
    return {"ok": True}


@router.post("/test")
def test_model(body: TestIn):
    conf = cfgmod.load_config()
    if body.kind == "stt" and body.entry not in conf.stt.providers:
        raise HTTPException(400, f"unknown speech-to-text entry {body.entry!r}")
    return models.test_stt(conf, body.entry) if body.kind == "stt" else models.test_notes(conf, body.entry)
