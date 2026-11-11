"""Updates for the Windows app: a new installer on GitHub (release `verbatim-v<version>`), installed with one click.

Only for Verbatim installed by the Windows installer (the environment sits in <install>\\verbatim\\.venv next to
uv.exe); on Linux it does nothing. Checked at most once a day (cached in <cache>/update.json). Updating: download
the installer, check its SHA-256 against GitHub's digest, start it silently with the current lectures folder and
Whisper choice, and quit; the installer reopens Verbatim (/RELAUNCH=1).
"""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
import time
from importlib import metadata
from pathlib import Path
from typing import Any

from . import config as cfgmod
from . import oscompat
from .util import read_json, write_json

RELEASES = "https://api.github.com/repos/StanLoobuyck/trivium/releases?per_page=30"
TAG = re.compile(r"^verbatim-v(\d+)\.(\d+)\.(\d+)$")
CHECK_EVERY_S = 24 * 3600


def current_version() -> str:
    return metadata.version("lecture-transcriber")


def _tuple(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def install_dir() -> Path | None:
    """<install> when this is the Windows app made by the installer, else None."""
    if not oscompat.WINDOWS:
        return None
    root = Path(sys.prefix).parent.parent  # <install>\verbatim\.venv → <install>
    return root if (root / "uv.exe").is_file() else None


def latest(releases: list[dict]) -> dict[str, Any] | None:
    """The newest verbatim-v release that carries an installer: {version, url, sha256, notes, page}."""
    best = None
    for r in releases:
        m = TAG.match(r.get("tag_name", ""))
        if not m or r.get("draft") or r.get("prerelease"):
            continue
        exe = next((a for a in r.get("assets", []) if re.fullmatch(r"Verbatim-Setup-[\d.]+\.exe", a.get("name", ""))), None)
        if not exe:
            continue
        version = ".".join(m.groups())
        if best is None or _tuple(version) > _tuple(best["version"]):
            digest = exe.get("digest") or ""
            best = {"version": version, "url": exe["browser_download_url"], "size": exe.get("size"),
                    "sha256": digest.removeprefix("sha256:") if digest.startswith("sha256:") else None,
                    "notes": (r.get("body") or "").strip()[:2000], "page": r.get("html_url")}
    return best


def check(force: bool = False, client: Any = None, now: float | None = None) -> dict[str, Any] | None:
    """A newer version than the one running, or None. Cached for a day; never raises (offline = no update)."""
    now = time.time() if now is None else now
    cache = cfgmod.cache_dir() / "update.json"
    data = read_json(cache) if cache.exists() else {}
    if force or now - data.get("checked", 0) > CHECK_EVERY_S:
        import httpx

        try:
            r = (client or httpx).get(RELEASES, timeout=15, headers={"Accept": "application/vnd.github+json"})
            r.raise_for_status()
            data = {"checked": now, "latest": latest(r.json())}
            write_json(cache, data)
        except (httpx.HTTPError, ValueError):
            pass
    new = data.get("latest")
    return new if new and _tuple(new["version"]) > _tuple(current_version()) else None


def download(new: dict[str, Any], client: Any = None) -> Path:
    """The installer in a temporary folder, after checking its SHA-256 (when GitHub gives one)."""
    import httpx

    path = Path(tempfile.mkdtemp(prefix="verbatim-update-")) / f"Verbatim-Setup-{new['version']}.exe"
    digest = hashlib.sha256()
    with (client or httpx).stream("GET", new["url"], follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with path.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)
                digest.update(chunk)
    if new.get("sha256") and digest.hexdigest() != new["sha256"]:
        path.unlink(missing_ok=True)
        raise ValueError("the downloaded installer doesn't match GitHub's checksum")
    return path


def installer_args(conf: cfgmod.Config) -> list[str]:
    """Silent update with the current choices; the installer reopens Verbatim afterwards."""
    from .settings import WHISPER_CHOICES

    whisper = next((k for k, v in WHISPER_CHOICES.items() if v == conf.stt.local.model), "accurate")
    return ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1",
            f"/LECTURES={conf.paths.jobs_dir.parent}", f"/WHISPER={whisper}"]


def cached() -> dict[str, Any] | None:
    """What the last check found (no network): for the banner."""
    cache = cfgmod.cache_dir() / "update.json"
    new = (read_json(cache) if cache.exists() else {}).get("latest")
    return new if new and _tuple(new["version"]) > _tuple(current_version()) else None


def busy(snapshot: dict[str, Any]) -> bool:
    """A lecture is being transcribed or gets notes right now: no update in the middle of it."""
    return any(i.get("status") in ("transcribing", "notes", "latex") for i in snapshot.get("items", []))


def start(conf: cfgmod.Config, new: dict[str, Any], client: Any = None) -> Path:
    """Download and start the installer; the caller quits the app right after."""
    import subprocess

    installer = download(new, client)
    subprocess.Popen([str(installer), *installer_args(conf)], **oscompat.detached())
    return installer
