"""Local web app (FastAPI on 127.0.0.1): JSON API + one static page in web/.

The API lives in api/, one router per area: add (find + upload + queue lectures), queue (queue, worker,
status), lectures (library + one lecture), setup (settings, courses, folders), models (Settings: added
models), archive (semesters + archive). Shared helpers in api/common.py.

Safety: binds to 127.0.0.1 only; rejects requests whose Host isn't localhost (DNS rebinding) and requires a
custom header on every write (a cross-site form or fetch from another website can't send it without CORS,
which is not enabled). Files are only served from job folders, looked up by job name — never by path.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

WEB_DIR = Path(__file__).parent / "web"
WRITE_HEADER = "x-lecture-ui"


def create_app() -> FastAPI:
    app = FastAPI(title="Verbatim", docs_url=None, redoc_url=None, openapi_url=None)
    from .api import add, archive, lectures, models, queue, setup

    for module in (add, queue, lectures, setup, models, archive):
        app.include_router(module.router)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        if request.method not in ("GET", "HEAD") and request.headers.get(WRITE_HEADER) != "1":
            return JSONResponse({"detail": "missing header"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/static/{name:path}")
    def static(name: str):
        # web/ files incl. the ES modules in web/js/<dir>/; every segment plain (no "..", no hidden files)
        path = WEB_DIR / name
        if not re.fullmatch(r"(?:\w[\w.-]*/)*\w[\w.-]*", name) or ".." in name or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    return app
