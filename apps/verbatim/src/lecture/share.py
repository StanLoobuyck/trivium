"""Share lectures through your own hub: whoever has a share code sees the lectures of the courses on that code
(video, transcript, subtitles, notes) at <hub>/share/, without access to Sequo. The codes live on the hub; this
module only keeps the hub's copy in step with the jobs: new or changed lectures go up, unshared ones come off.

Runs from the worker's idle round (at most `max_videos` uploads per round, so new recordings aren't held up) and
from the "sync now" button. A file lock keeps two processes from uploading the same thing.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import httpx

from . import config as cfgmod
from .util import read_json, write_json

TIMEOUT = httpx.Timeout(30.0, write=600.0)  # a 300 MB video over Tailscale takes ~15 s; leave room for slow links
READY = {"transcribed", "done", "notes_pending", "notes"}  # a transcript exists
SUMMARY_KEYS = ("id", "title", "date", "course", "course_name", "duration_s", "sections", "has_notes", "lesson",
                "part", "rank", "group", "semester")


def _link():
    from .hub import _auth
    return _auth(cfgmod.load_config())


def codes() -> dict:
    """The hub's share overview: {codes: [...], lectures: [...]}. Raises ValueError without a hub."""
    link = _link()
    if not link:
        raise ValueError("fill in the hub address and pairing code first")
    r = httpx.get(f"{link[0]}/api/share", headers=link[1], timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def hub_call(method: str, path: str, **kw) -> dict:
    link = _link()
    if not link:
        raise ValueError("fill in the hub address and pairing code first")
    r = httpx.request(method, f"{link[0]}{path}", headers=link[1], timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json()


def lecture_data(summary: dict, detail: dict) -> dict:
    """What the viewer gets: no file paths, models, queue state or corrections list."""
    return {"summary": {k: summary.get(k) for k in SUMMARY_KEYS},
            "segments": detail.get("segments", []),
            "sections_detail": detail.get("sections_detail", []),
            "notes": detail.get("notes"),
            "language": detail.get("language")}


def digest(data) -> str:
    raw = data if isinstance(data, bytes) else json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def plan(local: list[dict], remote: list[dict], shared_courses: set[str]) -> tuple[list[dict], list[str]]:
    """Which local lectures need (re)sending and which hub lectures must go. Pure: local items carry id, course,
    hash, video_size, subtitles_hash; remote items are what the hub reports."""
    have = {x["id"]: x for x in remote}
    wanted = [x for x in local if x["course"] in shared_courses]
    keys = ("course", "hash", "video_size", "subtitles_hash")
    send = [x for x in wanted if x["id"] not in have or any(have[x["id"]].get(k) != x[k] for k in keys)]
    ids = {x["id"] for x in wanted}
    return send, [i for i in have if i not in ids]


@contextmanager
def _lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _local(courses: set[str]) -> list[dict]:
    """Every lecture of these courses with a transcript, with what the hub should have of it."""
    from .api import lectures as api
    from .player import ensure_player

    out = []
    for summary in api.lectures():
        if not summary.get("id") or summary.get("status") not in READY or summary.get("course") not in courses:
            continue
        d = api.job_dir(summary["id"])
        if not (d / "sections.json").exists():
            continue
        detail = api.lecture(summary["id"])
        data = lecture_data(summary, detail)
        media = (read_json(d / "manifest.json").get("input") or {}).get("media")
        video = None
        if media and Path(media).is_file():
            video = ensure_player(d, Path(media)) or Path(media)
        subs = d / "outputs" / "subtitles.vtt"
        out.append({"id": summary["id"], "course": summary["course"], "hash": digest(data),
                    "video_size": video.stat().st_size if video else 0,
                    "subtitles_hash": digest(subs.read_bytes()) if subs.is_file() else "",
                    "_data": data, "_video": video, "_subs": subs if subs.is_file() else None})
    return out


def _status(local: list[dict], shared: set[str]) -> dict:
    return {"shared": sum(1 for x in local if x["course"] in shared)}


def _waiting(send: list[dict], by_id: dict, remote: dict) -> int:
    return sum(1 for item in send if by_id[item["id"]]["_video"]
               and remote.get(item["id"], {}).get("video_size") != by_id[item["id"]]["video_size"])


def sync(max_videos: int | None = None, log=print) -> dict:
    """Bring the hub up to date. Returns counts; status is written to jobs/share_status.json for the UI."""
    conf = cfgmod.load_config()
    jobs = conf.paths.jobs_dir
    status_path = jobs / "share_status.json"
    with _lock(jobs / "share.lock") as mine:
        if not mine:
            return {"busy": True}
        overview = codes()
        shared = {c["id"] for code in overview["codes"] for c in code["courses"]}
        local = _local(shared) if shared else []
        send, remove = plan([{k: v for k, v in x.items() if not k.startswith("_")} for x in local],
                            overview["lectures"], shared)
        by_id = {x["id"]: x for x in local}
        remote = {x["id"]: x for x in overview["lectures"]}
        videos = 0
        for lecture_id in remove:
            hub_call("DELETE", f"/api/share/lectures/{lecture_id}")
        # First every lecture's text and subtitles (seconds: the whole list is on the page at once), then the
        # videos (~15 s each); a lecture without its video yet says so on the page.
        for item in send:
            x, old = by_id[item["id"]], remote.get(item["id"], {})
            if old.get("hash") != x["hash"] or old.get("course") != x["course"]:
                hub_call("PUT", f"/api/share/lectures/{x['id']}", json={"course": x["course"], "hash": x["hash"],
                                                                         "data": x["_data"]})
            if x["_subs"] and old.get("subtitles_hash") != x["subtitles_hash"]:
                hub_call("PUT", f"/api/share/lectures/{x['id']}/subtitles", params={"hash": x["subtitles_hash"]},
                         content=x["_subs"].read_bytes())
        for item in send:
            x, old = by_id[item["id"]], remote.get(item["id"], {})
            if not x["_video"] or old.get("video_size") == x["video_size"]:
                continue
            if max_videos is not None and videos >= max_videos:
                break
            log(f"share: uploading {x['id']} ({x['video_size'] // 1_000_000} MB)")
            with x["_video"].open("rb") as f:
                hub_call("PUT", f"/api/share/lectures/{x['id']}/video", content=f)
            videos += 1
            write_json(status_path, {**_status(local, shared), "videos_waiting": _waiting(send, by_id, remote) - videos})
        result = {**_status(local, shared), "sent": len(send), "removed": len(remove), "videos": videos,
                  "videos_waiting": max(0, _waiting(send, by_id, remote) - videos)}
        write_json(status_path, result)
        return result


_last = {"at": 0.0}
EVERY_S = 300  # a full check reads every shared transcript (~1 s for 16 lectures): not every 30 s idle round


def sync_quietly(now: float | None = None) -> None:
    """From the worker: one video per run, at most every 5 min while all is sent (right away while videos wait);
    never fails the worker; without a hub nothing happens."""
    import time

    now = time.time() if now is None else now
    if now - _last["at"] < EVERY_S or not _link():
        return
    _last["at"] = now
    try:
        result = sync(max_videos=1, log=lambda m: print(m, flush=True))
        if result.get("videos_waiting"):
            _last["at"] = 0.0  # more to send: next idle round again
    except Exception as exc:  # noqa: BLE001
        print(f"share: {type(exc).__name__}: {exc}", flush=True)
