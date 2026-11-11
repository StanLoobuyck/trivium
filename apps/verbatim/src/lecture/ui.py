"""`lecture ui`: serve the local web app (webapp.py + web/) on 127.0.0.1 and open it in the browser.

The UI never transcribes itself: the worker (`lecture worker` / systemd user service) does, so closing the
browser or this process doesn't stop anything. A second launch (e.g. from the app launcher) only opens
the tab of the running instance.
"""

from __future__ import annotations

import threading

from . import oscompat


def url(port: int) -> str:
    return f"http://127.0.0.1:{port}/"


def already_running(port: int) -> bool:
    import httpx

    try:
        return "Lecture Transcriber" in httpx.get(url(port), timeout=2).text
    except httpx.HTTPError:
        return False


def open_browser(port: int) -> None:
    oscompat.open_with_desktop(url(port))


def serve(port: int = 7861, browser: bool = True) -> None:
    if already_running(port):
        if browser:
            open_browser(port)
        return
    import uvicorn

    from .webapp import create_app

    if browser:  # once the server accepts connections
        threading.Timer(1.0, open_browser, args=(port,)).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="warning")
