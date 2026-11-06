"""Verbatim delen: lessen (video, transcript, notities) om te bekijken met een eigen deelcode per persoon.

Gescheiden van Sequo: een deelcode opent alleen /share/api/…, nooit /api/… (sync, vakken, events). Beheer (codes
maken en intrekken, lessen uploaden) vraagt de koppelcode van de hub; dat doet Verbatim op de laptop.
Lessen staan als JSON in SQLite, video en ondertitels als bestand in <map van de database>/share/<les>/.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

COOKIE = "verbatim_share"
ID_RX = re.compile(r"^[\w.-]{1,160}$")
MAX_JSON = 20 * 1024 * 1024  # een les met transcript en notities is ~1 MB

SCHEMA = """
CREATE TABLE IF NOT EXISTS share_codes (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT UNIQUE NOT NULL, courses TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS share_lectures (
  id TEXT PRIMARY KEY, course TEXT NOT NULL, hash TEXT NOT NULL, data TEXT NOT NULL,
  video_size INTEGER NOT NULL DEFAULT 0, subtitles_hash TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL
);
"""


class CourseRef(BaseModel):
    id: str = Field(pattern=r"^[\w.-]{1,120}$")
    name: str = Field(max_length=200)
    color: str | None = Field(default=None, pattern=r"^[a-z]{1,20}$")  # palette key from packages/design


class CodeIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    courses: list[CourseRef] = Field(max_length=50)


class CodePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    courses: list[CourseRef] | None = Field(default=None, max_length=50)


class LectureIn(BaseModel):
    course: str = Field(pattern=r"^[\w.-]{1,120}$")
    hash: str = Field(max_length=80)
    data: dict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_id(lecture_id: str) -> str:
    if not ID_RX.match(lecture_id) or lecture_id.startswith("."):
        raise HTTPException(status_code=404)
    return lecture_id


async def _save_body(request: Request, target: Path) -> int:
    """Streamt de body naar een tijdelijk bestand en zet het pas op zijn plaats als alles binnen is."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    size = 0
    with part.open("wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
            size += len(chunk)
    part.replace(target)
    return size


def router(store, check_code, data_dir: Path) -> APIRouter:
    db = store.db
    db.executescript(SCHEMA)
    files = data_dir / "share"
    r = APIRouter()

    def code_row(row) -> dict:
        return {"id": row[0], "name": row[1], "code": row[2], "courses": json.loads(row[3]), "created": row[4]}

    def codes() -> list[dict]:
        return [code_row(x) for x in db.execute("SELECT id, name, code, courses, created FROM share_codes ORDER BY created")]

    def lecture_or_404(lecture_id: str) -> tuple[str, dict, int, str]:
        row = db.execute("SELECT course, data, video_size, subtitles_hash FROM share_lectures WHERE id = ?",
                         (_check_id(lecture_id),)).fetchone()
        if not row:
            raise HTTPException(status_code=404)
        return row[0], json.loads(row[1]), row[2], row[3]

    # --- beheer: koppelcode van de hub ----------------------------------------------------------------------
    admin = [Depends(check_code)]

    @r.get("/api/share", dependencies=admin)
    def overview() -> dict:
        rows = db.execute("SELECT id, course, hash, video_size, subtitles_hash FROM share_lectures").fetchall()
        return {"codes": codes(), "lectures": [{"id": x[0], "course": x[1], "hash": x[2], "video_size": x[3],
                                                "subtitles_hash": x[4]} for x in rows]}

    @r.post("/api/share/codes", dependencies=admin)
    def new_code(body: CodeIn) -> dict:
        row = (secrets.token_hex(8), body.name.strip(), secrets.token_urlsafe(18),
               json.dumps([c.model_dump() for c in body.courses]), _now())
        db.execute("INSERT INTO share_codes VALUES (?, ?, ?, ?, ?)", row)
        return code_row(row)

    @r.patch("/api/share/codes/{code_id}", dependencies=admin)
    def edit_code(code_id: str, body: CodePatch) -> dict:
        if body.name is not None:
            db.execute("UPDATE share_codes SET name = ? WHERE id = ?", (body.name.strip(), code_id))
        if body.courses is not None:
            db.execute("UPDATE share_codes SET courses = ? WHERE id = ?",
                       (json.dumps([c.model_dump() for c in body.courses]), code_id))
        found = [c for c in codes() if c["id"] == code_id]
        if not found:
            raise HTTPException(status_code=404)
        return found[0]

    @r.delete("/api/share/codes/{code_id}", dependencies=admin)
    def revoke(code_id: str) -> dict:
        db.execute("DELETE FROM share_codes WHERE id = ?", (code_id,))
        return {"ok": True}

    @r.put("/api/share/lectures/{lecture_id}", dependencies=admin)
    def put_lecture(lecture_id: str, body: LectureIn) -> dict:
        _check_id(lecture_id)
        data = json.dumps(body.data)
        if len(data) > MAX_JSON:
            raise HTTPException(status_code=413)
        db.execute("""INSERT INTO share_lectures (id, course, hash, data, updated) VALUES (?, ?, ?, ?, ?)
                      ON CONFLICT(id) DO UPDATE SET course = excluded.course, hash = excluded.hash,
                      data = excluded.data, updated = excluded.updated""",
                   (lecture_id, body.course, body.hash, data, _now()))
        return {"ok": True}

    @r.put("/api/share/lectures/{lecture_id}/video", dependencies=admin)
    async def put_video(lecture_id: str, request: Request) -> dict:
        lecture_or_404(lecture_id)
        size = await _save_body(request, files / lecture_id / "video.mp4")
        db.execute("UPDATE share_lectures SET video_size = ? WHERE id = ?", (size, lecture_id))
        return {"size": size}

    @r.put("/api/share/lectures/{lecture_id}/subtitles", dependencies=admin)
    async def put_subtitles(lecture_id: str, request: Request, hash: str = "") -> dict:
        lecture_or_404(lecture_id)
        await _save_body(request, files / lecture_id / "subtitles.vtt")
        db.execute("UPDATE share_lectures SET subtitles_hash = ? WHERE id = ?", (hash[:80], lecture_id))
        return {"ok": True}

    @r.delete("/api/share/lectures/{lecture_id}", dependencies=admin)
    def delete_lecture(lecture_id: str) -> dict:
        db.execute("DELETE FROM share_lectures WHERE id = ?", (_check_id(lecture_id),))
        shutil.rmtree(files / lecture_id, ignore_errors=True)
        return {"ok": True}

    # --- bekijken: deelcode, bewaard in een cookie zodat ook <video> en <track> mogen ---------------------------
    def viewer(verbatim_share: str = Cookie(default="")) -> dict:
        for c in codes():
            if verbatim_share and secrets.compare_digest(c["code"].encode(), verbatim_share.encode()):
                return c
        raise HTTPException(status_code=401)

    def allowed(code: dict, lecture_id: str) -> tuple[dict, int, str]:
        course, data, video_size, subs = lecture_or_404(lecture_id)
        if course not in {c["id"] for c in code["courses"]}:
            raise HTTPException(status_code=404)
        return data, video_size, subs

    @r.post("/share/api/login")
    def login(body: dict, request: Request, response: Response) -> dict:
        code = str(body.get("code", ""))
        match = next((c for c in codes() if code and secrets.compare_digest(c["code"].encode(), code.encode())), None)
        if not match:
            raise HTTPException(status_code=401)
        https = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
        response.set_cookie(COOKIE, code, max_age=400 * 24 * 3600, httponly=True, samesite="strict", secure=https,
                            path="/share")
        return {"name": match["name"]}

    @r.post("/share/api/logout")
    def logout(response: Response) -> dict:
        response.delete_cookie(COOKIE, path="/share")
        return {"ok": True}

    @r.get("/share/api/me")
    def me(code: dict = Depends(viewer)) -> dict:
        return {"name": code["name"], "courses": code["courses"]}

    @r.get("/share/api/lectures")
    def lectures(code: dict = Depends(viewer)) -> list[dict]:
        ids = [c["id"] for c in code["courses"]]
        if not ids:
            return []
        rows = db.execute(f"SELECT data, video_size FROM share_lectures WHERE course IN ({','.join('?' * len(ids))})",
                          ids).fetchall()
        out = []
        for data, video_size in rows:
            summary = json.loads(data).get("summary", {})
            out.append({**summary, "has_video": video_size > 0})
        return out

    @r.get("/share/api/lectures/{lecture_id}")
    def lecture(lecture_id: str, code: dict = Depends(viewer)) -> dict:
        data, video_size, subs = allowed(code, lecture_id)
        return {**data, "has_video": video_size > 0, "has_subtitles": bool(subs)}

    def download_name(data: dict, ext: str) -> str:
        s = data.get("summary", {})
        name = " - ".join(x for x in (s.get("course_name"), s.get("title")) if x) or "les"
        return re.sub(r'[\\/:*?"<>|]+', " ", name).strip() + ext

    @r.get("/share/api/lectures/{lecture_id}/video")
    def video(lecture_id: str, download: bool = False, code: dict = Depends(viewer)):
        data, video_size, _ = allowed(code, lecture_id)
        path = files / lecture_id / "video.mp4"
        if not video_size or not path.is_file():
            raise HTTPException(status_code=404)
        # FileResponse kent Range: de speler kan spoelen
        return FileResponse(path, media_type="video/mp4",
                            filename=download_name(data, ".mp4") if download else None,
                            content_disposition_type="attachment" if download else "inline")

    @r.get("/share/api/lectures/{lecture_id}/subtitles.vtt")
    def subtitles(lecture_id: str, download: bool = False, code: dict = Depends(viewer)):
        data, _, subs = allowed(code, lecture_id)
        path = files / lecture_id / "subtitles.vtt"
        if not subs or not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="text/vtt; charset=utf-8", headers={"Cache-Control": "no-cache"},
                            filename=download_name(data, ".vtt") if download else None,
                            content_disposition_type="attachment" if download else "inline")

    @r.get("/share/api/lectures/{lecture_id}/transcript.txt")
    def transcript(lecture_id: str, code: dict = Depends(viewer)):
        data, _, _ = allowed(code, lecture_id)

        def ts(s: float) -> str:
            s = int(s)
            return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
        text = "\n".join(f"[{ts(g['start'])}] {g['text']}" for g in data.get("segments", []))
        name = download_name(data, ".txt")
        return PlainTextResponse(text + "\n", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_quote(name)}"})

    return r


def _quote(name: str) -> str:
    from urllib.parse import quote
    return quote(name)
