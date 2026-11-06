"""De API van de hub. Elke route onder /api behalve /health vraagt de koppelcode; /share/ is Verbatim delen (share.py)."""
import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import share
from .rooster import fetch_loop
from .store import TABLES, Store

MIN_CODE_LENGTH = 32
MAX_CHANGES = 5000


class Change(BaseModel):
    table: str
    record: dict


class Event(BaseModel, extra="allow"):
    """Zie packages/contract/CONTRACT.md. De hub bewaart events; Sequo beslist wat ze betekenen."""

    id: str
    type: Literal["notes.ready"]
    source: Literal["verbatim"]
    occurredAt: str
    payload: dict


class SyncRequest(BaseModel):
    cursor: int = 0
    changes: list[Change] = []


def create_app(*, code: str, db_path: str | Path, web_dir: str | None = None, rooster_url: str | None = None,
               share_web: str | None = None) -> FastAPI:
    if len(code) < MIN_CODE_LENGTH:
        raise ValueError(f"De koppelcode moet minstens {MIN_CODE_LENGTH} tekens hebben")
    store = Store(db_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        task = asyncio.create_task(fetch_loop(store, rooster_url)) if rooster_url else None
        yield
        if task:
            task.cancel()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def check_code(authorization: str = Header(default="")) -> None:
        if not secrets.compare_digest(authorization.encode(), f"Bearer {code}".encode()):
            raise HTTPException(status_code=401)

    @app.get("/api/health")
    def health() -> dict:
        return {"app": "trivium-hub"}

    @app.post("/api/sync", dependencies=[Depends(check_code)])
    def sync(request: SyncRequest) -> dict:
        if len(request.changes) > MAX_CHANGES:
            raise HTTPException(status_code=413)
        changes = [c.model_dump() for c in request.changes]
        for change in changes:
            record = change["record"]
            valid = isinstance(record.get("id"), str) and isinstance(record.get("updatedAt"), str)
            if change["table"] not in TABLES or not valid:
                raise HTTPException(status_code=422)
        store.apply(changes)
        records, cursor = store.since(request.cursor)
        return {"cursor": cursor, "records": records, "rooster": store.get_meta("rooster_hash")}

    @app.post("/api/events", dependencies=[Depends(check_code)])
    def add_event(event: Event) -> dict:
        store.add_event(event.model_dump())
        return {"ok": True}

    @app.get("/api/events", dependencies=[Depends(check_code)])
    def events(after: int = 0) -> dict:
        found, cursor = store.events_since(after)
        return {"events": found, "cursor": cursor}

    @app.get("/api/courses", dependencies=[Depends(check_code)])
    def courses() -> dict:
        return {"courses": store.active_courses()}

    @app.get("/api/rooster", dependencies=[Depends(check_code)])
    def rooster() -> dict:
        text = store.get_meta("rooster_text")
        if text is None:
            raise HTTPException(status_code=404)
        return {"hash": store.get_meta("rooster_hash"), "text": text, "fetchedAt": store.get_meta("rooster_fetched_at")}

    app.include_router(share.router(store, check_code, Path(db_path).resolve().parent))
    # De pagina om te bekijken komt uit Verbatim (deploy-hub.sh zet apps/verbatim/src/lecture/web in share-web/).
    if share_web and Path(share_web).is_dir():
        @app.get("/share/", include_in_schema=False)
        def share_page() -> FileResponse:
            return FileResponse(Path(share_web) / "share.html", headers={"Cache-Control": "no-cache"})
        app.mount("/share/static", StaticFiles(directory=share_web), name="share-web")

    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def from_env() -> FastAPI:
    return create_app(
        code=os.environ["HUB_CODE"],
        db_path=os.environ.get("HUB_DB", "hub.sqlite"),
        web_dir=os.environ.get("HUB_WEB"),
        rooster_url=os.environ.get("ROOSTER_URL"),
        share_web=os.environ.get("HUB_SHARE_WEB", "share-web"),
    )
