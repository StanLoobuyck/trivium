"""/api/queue, the worker and the dashboard's status and today strip."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config as cfgmod
from ..naming import guess_title
from ..util import read_json
from . import common
from .common import step_model

router = APIRouter()


class Paused(BaseModel):
    paused: bool


@router.get("/api/queue")
def queue_list():
    conf = cfgmod.load_config()
    snap = common.Queue().snapshot()
    items = []
    for i in snap["items"]:
        title = i.get("title")
        if not title and i.get("job") and (Path(i["job"]) / "manifest.json").exists():
            title = read_json(Path(i["job"]) / "manifest.json").get("title")
        items.append({**i, "display_title": title or guess_title(Path(i["media"]).stem),
                      "step_model": step_model(i, conf)})
    return {"items": items, "notes_paused": snap["notes_paused"], "worker": common.worker_running()}


@router.post("/api/queue/clear-done")
def clear_done():
    return {"removed": common.Queue().clear_done()}


@router.post("/api/queue/{item_id}/{action}")
def queue_action(item_id: str, action: str):
    q = common.Queue()
    try:
        if action == "retry":
            q.retry(item_id)
        elif action == "remove":
            q.remove(item_id)
        else:
            raise HTTPException(404)
    except KeyError as exc:
        raise HTTPException(409, str(exc).strip("'")) from None
    return {"ok": True}


@router.post("/api/notes-paused")
def set_paused(body: Paused):
    common.Queue().set_notes_paused(body.paused)
    return {"paused": body.paused}


@router.get("/api/status")
def status():
    from ..status import gather

    return gather(cfgmod.load_config())


@router.post("/api/worker/start")
def start_worker():
    if common.worker_running():
        return {"started": False, "running": True}
    log = cfgmod.cache_dir() / "worker.log"
    with log.open("a") as fh:
        subprocess.Popen([sys.executable, "-m", "lecture.cli", "worker"], stdout=fh, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    return {"started": True, "log": str(log)}


@router.get("/api/today")
def today():
    return {"date": date.today().isoformat()}


_inbox_cache: dict = {"at": 0.0, "data": None}


@router.get("/api/inbox")
def inbox_waiting():
    """Recordings in the watch folder's course folders that wait (no slides yet, still copying, …).
    Cached 10 s: the dashboard asks every 3 s and this reads every job's manifest."""
    import time

    from .. import inbox

    if time.monotonic() - _inbox_cache["at"] > 10 or _inbox_cache["data"] is None:
        conf = cfgmod.load_config()
        courses = cfgmod.load_courses()
        inbox.ensure_folders(conf, courses)
        _inbox_cache.update(at=time.monotonic(), data={
            "root": str(conf.paths.inbox_dir),
            "waiting": [f for f in inbox.scan(conf, courses) if not f["ready"]]})
    return _inbox_cache["data"]
