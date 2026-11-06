"""Settings → Share: share codes on the hub (name + courses) and syncing the shared lectures to it (share.py)."""

from __future__ import annotations

import threading

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import config as cfgmod
from .. import share
from ..util import read_json
from .common import jobs_dir

router = APIRouter()
_running = {"sync": False, "error": None}


class CodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    courses: list[str] = Field(max_length=50)
    colors: dict[str, str] = {}  # course id → palette key, as the page shows it (same colour for the viewer)


class CodePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    courses: list[str] | None = Field(default=None, max_length=50)
    colors: dict[str, str] = {}


def _refs(ids: list[str], colors: dict[str, str] | None = None) -> list[dict]:
    names = {c.id: c.name for c in cfgmod.load_courses()}
    unknown = [i for i in ids if i not in names]
    if unknown:
        raise HTTPException(400, f"unknown course: {', '.join(unknown)}")
    colors = colors or {}
    return [{"id": i, "name": names[i], **({"color": colors[i]} if colors.get(i, "").isalpha() else {})} for i in ids]


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"hub: {exc}") from None


def _link(code: str) -> str:
    return f"{cfgmod.load_config().hub.url.rstrip('/')}/share/#{code}"


@router.get("/api/share")
def overview():
    status_path = jobs_dir() / "share_status.json"
    status = read_json(status_path) if status_path.exists() else None
    try:
        data = share.codes()
    except ValueError:
        return {"hub": False, "codes": [], "status": status, "syncing": _running["sync"]}
    except httpx.HTTPError as exc:
        return {"hub": True, "error": str(exc), "codes": [], "status": status, "syncing": _running["sync"]}
    codes = [{**c, "link": _link(c["code"])} for c in data["codes"]]
    return {"hub": True, "codes": codes, "status": status, "on_hub": len(data["lectures"]),
            "syncing": _running["sync"], "sync_error": _running["error"]}


@router.post("/api/share/codes")
def new_code(body: CodeIn):
    code = _call(share.hub_call, "POST", "/api/share/codes", json={"name": body.name, "courses": _refs(body.courses, body.colors)})
    start_sync()
    return {**code, "link": _link(code["code"])}


@router.patch("/api/share/codes/{code_id}")
def edit_code(code_id: str, body: CodePatch):
    patch = {"name": body.name} if body.name is not None else {}
    if body.courses is not None:
        patch["courses"] = _refs(body.courses, body.colors)
    code = _call(share.hub_call, "PATCH", f"/api/share/codes/{code_id}", json=patch)
    start_sync()
    return {**code, "link": _link(code["code"])}


@router.delete("/api/share/codes/{code_id}")
def revoke(code_id: str):
    _call(share.hub_call, "DELETE", f"/api/share/codes/{code_id}")
    start_sync()  # lectures nobody can see any more come off the hub
    return {"ok": True}


@router.post("/api/share/sync")
def start_sync():
    """Everything at once (all videos), in the background; the page polls GET /api/share."""
    if _running["sync"]:
        return {"started": False}
    _running["sync"], _running["error"] = True, None

    def run():
        try:
            share.sync()
        except Exception as exc:  # noqa: BLE001 - shown in Settings
            _running["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            _running["sync"] = False
    threading.Thread(target=run, daemon=True).start()
    return {"started": True}
