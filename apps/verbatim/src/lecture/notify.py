"""Desktop notifications. Linux: notify-send (shown by DMS). In `lecture app` the tray icon shows them
(Windows, macOS). Silent if neither is there."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable

_backend: Callable[[str, str], None] | None = None


def set_backend(show: Callable[[str, str], None] | None) -> None:
    """Send notifications to `show(title, body)` instead (the tray icon of `lecture app`)."""
    global _backend
    _backend = show


def notify(title: str, body: str = "", urgency: str = "normal") -> None:
    if _backend is not None:
        try:
            _backend(title, body)
        except Exception:  # noqa: BLE001 — a notification must never stop the worker
            pass
        return
    if not shutil.which("notify-send"):
        return
    try:
        subprocess.run(
            ["notify-send", "--app-name=Lecture Transcriber", f"--urgency={urgency}", title, body],
            timeout=5, check=False, capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        pass
