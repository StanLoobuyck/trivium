"""De API van de hub. Elke route onder /api behalve /health vraagt de koppelcode."""
import asyncio
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .rooster import fetch_loop
from .store import TABLES, Store

MIN_CODE_LENGTH = 32
MAX_CHANGES = 5000


class Change(BaseModel):
    table: str
    record: dict


class SyncRequest(BaseModel):
    cursor: int = 0
    changes: list[Change] = []


def create_app(*, code: str, db_path: str | Path, web_dir: str | None = None, rooster_url: str | None = None) -> FastAPI:
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
        return {"app": "inhaal-hub"}

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

    @app.get("/api/rooster", dependencies=[Depends(check_code)])
    def rooster() -> dict:
        text = store.get_meta("rooster_text")
        if text is None:
            raise HTTPException(status_code=404)
        return {"hash": store.get_meta("rooster_hash"), "text": text, "fetchedAt": store.get_meta("rooster_fetched_at")}

    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def from_env() -> FastAPI:
    return create_app(
        code=os.environ["HUB_CODE"],
        db_path=os.environ.get("HUB_DB", "hub.sqlite"),
        web_dir=os.environ.get("HUB_WEB"),
        rooster_url=os.environ.get("ROOSTER_URL"),
    )
