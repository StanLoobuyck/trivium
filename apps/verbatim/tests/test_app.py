"""`lecture app`: UI + worker in one process, tray icon with Quit, notifications through the tray."""

import socket
import threading

import httpx

from lecture import app, notify, queue


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeIcon:
    def __init__(self, port, quit_app):
        self.port, self.quit_app, self.shown = port, quit_app, []
        self.stopped = threading.Event()

    def notify(self, body, title):
        self.shown.append((title, body))

    def run(self):
        self.page = httpx.get(f"http://127.0.0.1:{self.port}/", timeout=5).text
        notify.notify("Les 3", "Notes ready")
        self.quit_app()  # the Quit menu item
        assert self.stopped.wait(5)

    def stop(self):
        self.stopped.set()


def test_app_serves_ui_runs_worker_and_quits(xdg, monkeypatch):
    port, started, icons = _free_port(), threading.Event(), []
    monkeypatch.setattr(queue, "work", lambda conf: started.set())
    monkeypatch.setattr(app, "_tray", lambda p, q: icons.append(FakeIcon(p, q)) or icons[-1])
    app.run(port, browser=False)  # returns after Quit
    icon = icons[0]
    assert "<title>Verbatim</title>" in icon.page
    assert started.wait(5)
    assert icon.shown == [("Les 3", "Notes ready")]
    assert notify._backend is None
    with httpx.Client() as client:  # the server is gone after Quit
        try:
            client.get(f"http://127.0.0.1:{port}/", timeout=1)
            raise AssertionError("UI still answers after Quit")
        except httpx.HTTPError:
            pass


def test_second_start_only_opens_the_tab(monkeypatch):
    opened = []
    monkeypatch.setattr(app.ui, "already_running", lambda port: True)
    monkeypatch.setattr(app.ui, "open_browser", opened.append)
    app.run(7999)
    assert opened == [7999]


def test_already_running_recognises_the_running_ui(xdg, monkeypatch):
    port = _free_port()
    seen = []

    class Icon(FakeIcon):
        def run(self):
            seen.append(app.ui.already_running(self.port))
            self.quit_app()

    monkeypatch.setattr(queue, "work", lambda conf: None)
    monkeypatch.setattr(app, "_tray", lambda p, q: Icon(p, q))
    assert not app.ui.already_running(port)
    app.run(port, browser=False)
    assert seen == [True]
