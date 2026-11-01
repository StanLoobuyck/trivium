"""Desktop notifications via notify-send (shown by DMS). Silent if unavailable."""

from __future__ import annotations

import shutil
import subprocess


def notify(title: str, body: str = "", urgency: str = "normal") -> None:
    if not shutil.which("notify-send"):
        return
    try:
        subprocess.run(
            ["notify-send", "--app-name=Lecture Transcriber", f"--urgency={urgency}", title, body],
            timeout=5, check=False, capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        pass
