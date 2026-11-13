"""Windows: replacing or reading a file another process has open fails for a moment (WinError 5/32). A G14 lost
Les 14 to it (2026-11-13): write_json and read_json now retry there for a few seconds."""

import os
import types

import pytest

from lecture import util


@pytest.fixture
def windows(monkeypatch):
    slept = []
    monkeypatch.setattr(util, "_WINDOWS", True)
    monkeypatch.setattr(util, "time", types.SimpleNamespace(sleep=slept.append))
    return slept


def flaky(real, fails):
    left = [fails]

    def call(*a, **k):
        if left[0]:
            left[0] -= 1
            raise PermissionError(13, "Access is denied")
        return real(*a, **k)
    return call


def test_write_survives_a_short_lock(tmp_path, monkeypatch, windows):
    path = tmp_path / "manifest.json"
    util.write_json(path, {"v": 1})
    monkeypatch.setattr(util.os, "replace", flaky(os.replace, 3))
    util.write_json(path, {"v": 2})
    assert util.read_json(path) == {"v": 2} and len(windows) == 3
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]       # no .tmp left behind


def test_write_gives_up_on_a_lasting_lock_and_cleans_up(tmp_path, monkeypatch, windows):
    path = tmp_path / "manifest.json"
    util.write_json(path, {"v": 1})
    monkeypatch.setattr(util.os, "replace", flaky(os.replace, 99))
    with pytest.raises(PermissionError):
        util.write_json(path, {"v": 2})
    assert util.read_json(path) == {"v": 1} and sum(windows) < 5
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]


def test_read_survives_a_short_lock(tmp_path, monkeypatch, windows):
    path = tmp_path / "manifest.json"
    util.write_json(path, {"v": 1})
    monkeypatch.setattr(util.Path, "read_text", flaky(util.Path.read_text, 2))
    assert util.read_json(path) == {"v": 1} and len(windows) == 2


def test_no_retry_outside_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(util, "_WINDOWS", False)
    monkeypatch.setattr(util.os, "replace", flaky(os.replace, 1))
    with pytest.raises(PermissionError):
        util.write_json(tmp_path / "x.json", {})
