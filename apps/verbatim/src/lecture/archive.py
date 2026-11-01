"""Move archived lectures' video/audio copies to the Mac at home, and back.

Only the app's own copies move: the player copy (media/player.mp4), audio/full.flac and, for lectures
uploaded through the browser, the upload copy in inbox/uploads. Transcripts, parts, notes and slides stay
(small; latex-notes needs them). The user's original recordings (e.g. ~/Videos/Recordings) are never moved.

Safe order: copy (rsync) → compare SHA-256 on both sides → only then delete the local file. The manifest
records what is where (`archive`), so the lecture page can say "video is on the Mac" and restore it.
`remote` is "host:dir" (ssh alias, e.g. "mac:lecture-archive") or a local directory (tests).
"""

from __future__ import annotations

import hashlib
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config as cfgmod
from .job import Job
from .util import read_json, write_json


class ArchiveError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _split(remote: str) -> tuple[str | None, str]:
    host, sep, path = remote.partition(":")
    return (host, path) if sep and "/" not in host else (None, remote)


def _run(cmd: list[str], timeout: float = 3600) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise ArchiveError(f"{cmd[0]} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout


def _remote_sha256(remote: str, rel: str) -> str:
    host, base = _split(remote)
    if host is None:
        return _sha256(Path(base) / rel)
    # macOS: shasum; Linux: sha256sum. The path is quoted for the remote shell.
    target = shlex.quote(f"{base}/{rel}")
    out = _run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
                f"cd ~ && (shasum -a 256 {target} 2>/dev/null || sha256sum {target})"], timeout=600)
    return out.split()[0]


def _mkdir(remote: str, rel_dir: str) -> None:
    host, base = _split(remote)
    if host is None:
        (Path(base) / rel_dir).mkdir(parents=True, exist_ok=True)
    else:
        _run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
              f"mkdir -p {shlex.quote(f'{base}/{rel_dir}')}"], timeout=60)


def _copy(src: str, dst: str) -> None:
    _run(["rsync", "-a", "--partial", "-e", "ssh -o BatchMode=yes -o ConnectTimeout=10", src, dst])


def media_files(job_root: Path) -> list[tuple[str, Path]]:
    """(name in the archive, local path) of the app's own media copies of this lecture that exist now."""
    m = read_json(job_root / "manifest.json")
    files = [("player.mp4", job_root / "media" / "player.mp4"), ("full.flac", job_root / "audio" / "full.flac")]
    media = m.get("input", {}).get("media")
    uploads = cfgmod.load_config().paths.inbox_dir / "uploads"
    if media and Path(media).parent == uploads:
        files.append(("upload/" + Path(media).name, Path(media)))
    return [(rel, p) for rel, p in files if p.is_file()]


def status(job_root: Path) -> dict[str, Any]:
    m = read_json(job_root / "manifest.json")
    a = m.get("archive") or {}
    local = media_files(job_root)
    return {"on_mac": bool(a.get("files")) and not a.get("restored"), "files": a.get("files", []),
            "local_bytes": sum(p.stat().st_size for _, p in local), "remote": a.get("remote")}


def move_to_remote(job_root: Path, remote: str | None = None, progress=None) -> dict[str, Any]:
    """Copy this lecture's media copies to the remote, verify, delete locally. Returns what moved."""
    remote = remote or cfgmod.load_config().archive.remote
    job = Job(job_root)
    with job.lock():
        files = media_files(job_root)
        if not files:
            return {"moved": 0, "bytes": 0}
        base_rel = job_root.name
        _mkdir(remote, base_rel + "/upload" if any(r.startswith("upload/") for r, _ in files) else base_rel)
        record, moved_bytes = [], 0
        for i, (rel, path) in enumerate(files):
            if progress:
                progress(f"{job_root.name}: {rel}", i, len(files))
            local_sha = _sha256(path)
            _copy(str(path), f"{remote}/{base_rel}/{rel}")
            if _remote_sha256(remote, f"{base_rel}/{rel}") != local_sha:
                raise ArchiveError(f"{rel}: the copy on {remote} differs from the original — nothing deleted")
            record.append({"name": rel, "path": str(path), "size": path.stat().st_size, "sha256": local_sha})
        # everything verified: now free the space
        for entry in record:
            Path(entry["path"]).unlink()
            moved_bytes += entry["size"]
        job.manifest["archive"] = {"remote": f"{remote}/{base_rel}", "files": record,
                                   "at": datetime.now().isoformat(timespec="seconds"), "restored": False}
        job.save()
    return {"moved": len(record), "bytes": moved_bytes}


def restore(job_root: Path, progress=None) -> dict[str, Any]:
    """Copy the media back from the remote (verified); the remote copy stays as a backup."""
    job = Job(job_root)
    with job.lock():
        a = job.manifest.get("archive") or {}
        if not a.get("files"):
            raise ArchiveError("this lecture has no media in the archive")
        restored = 0
        for i, entry in enumerate(a["files"]):
            if progress:
                progress(f"{job_root.name}: {entry['name']}", i, len(a["files"]))
            dest = Path(entry["path"])
            if dest.is_file() and _sha256(dest) == entry["sha256"]:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_name(dest.name + ".part")
            _copy(f"{a['remote']}/{entry['name']}", str(part))
            if _sha256(part) != entry["sha256"]:
                part.unlink(missing_ok=True)
                raise ArchiveError(f"{entry['name']}: restored copy differs — kept on the remote, try again")
            part.rename(dest)
            restored += 1
        a["restored"] = True
        a["restored_at"] = datetime.now().isoformat(timespec="seconds")
        job.save()
    return {"restored": restored}
