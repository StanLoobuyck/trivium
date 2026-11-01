"""Small shared helpers: atomic JSON files, hashing, time formatting."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


def find_claude() -> str | None:
    """Path of the `claude` CLI. Also looks in its usual install folders: the app launcher and systemd start
    us with a PATH that has no ~/.local/bin, so `which` alone reports Claude Code as missing."""
    found = shutil.which("claude")
    if found:
        return found
    for cand in (Path.home() / ".local/bin/claude", Path.home() / ".claude/local/claude"):
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically (temp file + rename), so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_data(data: Any) -> str:
    """Stable short hash of JSON-serialisable data."""
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def file_fingerprint(path: Path, edge_bytes: int = 8 * 1024 * 1024) -> str:
    """Fast fingerprint of a (possibly huge) file: size + SHA-256 of the first and last 8 MB.

    mtime is left out on purpose: copying a lecture to another folder shouldn't invalidate work.
    """
    size = path.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with path.open("rb") as fh:
        h.update(fh.read(edge_bytes))
        if size > edge_bytes:
            fh.seek(max(edge_bytes, size - edge_bytes))
            h.update(fh.read(edge_bytes))
    return h.hexdigest()[:16]


def fmt_ts(seconds: float) -> str:
    """12.3 → '00:00:12'."""
    s = int(max(0.0, seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_ts(text: str) -> float:
    """'1:02:03', '62:03', '3723' or '3723.5' → seconds."""
    parts = text.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"bad timestamp: {text!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def slugify(text: str, max_len: int = 40) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:max_len].strip("-") or "lecture"
