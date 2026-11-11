"""Updates of the Windows app: the newest verbatim-v release with an installer, checked once a day."""

import hashlib

import httpx
import pytest

from lecture import updates
from lecture.config import load_config


def release(tag, exe=True, digest=None, draft=False, body="Fixes"):
    assets = [{"name": f"Verbatim-Setup-{tag.split('v')[-1]}.exe", "browser_download_url": f"https://x/{tag}.exe",
               "size": 10, "digest": digest}] if exe else []
    return {"tag_name": tag, "assets": assets, "draft": draft, "prerelease": False, "body": body, "html_url": f"https://x/{tag}"}


RELEASES = [release("velox-v9.9.9"), release("verbatim-v0.3.0", exe=False), release("verbatim-v0.2.10", digest="sha256:ab"),
            release("verbatim-v0.2.9"), release("verbatim-v0.4.0", draft=True)]


def test_latest_is_the_newest_with_an_installer():
    new = updates.latest(RELEASES)
    assert new["version"] == "0.2.10" and new["sha256"] == "ab" and new["url"].endswith("verbatim-v0.2.10.exe")
    assert updates.latest([]) is None


class Client:
    def __init__(self, releases=RELEASES, fail=False):
        self.calls, self.releases, self.fail = 0, releases, fail

    def get(self, url, timeout, headers):
        self.calls += 1
        if self.fail:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json=self.releases, request=httpx.Request("GET", url))


T = 1_800_000_000  # a real timestamp: "never checked" is more than a day ago


def test_check_once_a_day_and_only_newer(xdg, monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "0.2.1")
    c = Client()
    assert updates.check(client=c, now=T)["version"] == "0.2.10"
    assert updates.check(client=c, now=T + 3600)["version"] == "0.2.10" and c.calls == 1  # cached
    updates.check(client=c, now=T + 25 * 3600)
    assert c.calls == 2
    monkeypatch.setattr(updates, "current_version", lambda: "0.2.10")
    assert updates.check(client=c, now=T) is None and updates.cached() is None


def test_offline_means_no_update(xdg):
    assert updates.check(client=Client(fail=True), now=T) is None


class Download:
    def __init__(self, data):
        self.data = data

    def stream(self, method, url, follow_redirects, timeout):
        data = self.data

        class Ctx:
            def __enter__(self):
                return httpx.Response(200, content=data, request=httpx.Request(method, url))

            def __exit__(self, *a):
                return False

        return Ctx()


def test_download_checks_the_checksum(xdg):
    good = hashlib.sha256(b"installer").hexdigest()
    path = updates.download({"version": "0.2.0", "url": "https://x/a.exe", "sha256": good}, Download(b"installer"))
    assert path.read_bytes() == b"installer"
    with pytest.raises(ValueError):
        updates.download({"version": "0.2.0", "url": "https://x/a.exe", "sha256": good}, Download(b"tampered"))


def test_installer_args_keep_the_choices(xdg, tmp_path):
    from lecture import settings

    settings.setup_simple(tmp_path / "Mijn lessen", "fast")
    args = updates.installer_args(load_config())
    assert "/SILENT" in args and "/RELAUNCH=1" in args and "/WHISPER=fast" in args
    assert f"/LECTURES={(tmp_path / 'Mijn lessen').resolve()}" in args


def test_busy_and_not_installed():
    assert updates.busy({"items": [{"status": "transcribing"}]})
    assert not updates.busy({"items": [{"status": "done"}, {"status": "queued"}]})
    assert updates.install_dir() is None  # not the Windows app
