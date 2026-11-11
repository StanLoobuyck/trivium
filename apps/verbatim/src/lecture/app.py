"""`lecture app`: Verbatim as one program, for computers without the systemd worker (Windows, macOS).

Runs the web UI and the worker in this process and shows a tray icon (Open · Quit) that also shows the
notifications. Quitting stops both; unfinished work resumes on the next start (every stage resumes from its
saved work). If a worker already runs elsewhere (the systemd service on Linux), this one only serves the UI.
Without pystray (Linux) it runs without an icon until Ctrl+C.
"""

from __future__ import annotations

import threading
import time
from importlib import resources

from . import notify, ui

APP_NAME = "Verbatim"


def _worker(stop: threading.Event) -> None:
    from . import config as cfgmod
    from .queue import WorkerRunning, work

    try:
        work(cfgmod.load_config())
    except WorkerRunning:
        print("A worker already runs elsewhere: only serving the UI.", flush=True)
    except Exception as exc:  # noqa: BLE001 — keep the UI up and say why the worker stopped
        print(f"Worker stopped: {exc}", flush=True)
        notify.notify(APP_NAME, f"Worker stopped: {exc}")
    finally:
        stop.wait()


def _tray(port: int, quit_app):
    """The tray icon, or None when pystray (or a tray) isn't available."""
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return None
    with resources.files("lecture").joinpath("assets/verbatim.png").open("rb") as fh:
        image = Image.open(fh)
        image.load()
    menu = pystray.Menu(
        pystray.MenuItem(f"Open {APP_NAME}", lambda: ui.open_browser(port), default=True),
        pystray.MenuItem("Quit", lambda icon: quit_app()),
    )
    return pystray.Icon("verbatim", image, APP_NAME, menu)


def run(port: int = 7861, browser: bool = True) -> None:
    from . import oscompat

    oscompat.prepare_windows_app()
    if ui.already_running(port):
        if browser:
            ui.open_browser(port)
        return
    import uvicorn

    from .webapp import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, name="ui", daemon=True)
    server_thread.start()
    stop = threading.Event()
    threading.Thread(target=_worker, args=(stop,), name="worker", daemon=True).start()

    deadline = time.monotonic() + 15
    while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if browser and server.started:
        ui.open_browser(port)

    icon = None

    def quit_app() -> None:
        server.should_exit = True
        stop.set()
        if icon is not None:
            icon.stop()

    icon = _tray(port, quit_app)
    try:
        if icon is not None:
            notify.set_backend(lambda title, body: icon.notify(body or title, title))
            icon.run()  # blocks until Quit
        else:
            while server_thread.is_alive():
                server_thread.join(0.5)
    except KeyboardInterrupt:
        print("\nStopped; unfinished work resumes on the next start.", flush=True)
    finally:
        notify.set_backend(None)
        quit_app()
        server_thread.join(5)
    # The worker thread is a daemon: it ends with the process. Its lecture goes back to the queue on restart.
