"""Locks and process checks behave the same on every OS (CI also runs this on Windows)."""

import os
import subprocess
import sys

import pytest

from lecture import oscompat


def test_second_handle_cannot_take_a_held_lock(tmp_path):
    path = tmp_path / "x.lock"
    with path.open("w") as a, path.open("w") as b:
        oscompat.lock(a)
        with pytest.raises(BlockingIOError):
            oscompat.lock(b, blocking=False)
        oscompat.unlock(a)
        oscompat.lock(b, blocking=False)
        oscompat.unlock(b)


def test_closing_the_file_releases_the_lock(tmp_path):
    path = tmp_path / "x.lock"
    with path.open("w") as a:
        oscompat.lock(a)
    with path.open("w") as b:
        oscompat.lock(b, blocking=False)


def test_lock_held_by_another_process(tmp_path):
    path = tmp_path / "x.lock"
    code = ("import sys, time; from lecture import oscompat\n"
            "f = open(sys.argv[1], 'w'); oscompat.lock(f); print('locked', flush=True); time.sleep(30)")
    child = subprocess.Popen([sys.executable, "-c", code, str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "locked"
        with path.open("w") as fh, pytest.raises(BlockingIOError):
            oscompat.lock(fh, blocking=False)
    finally:
        child.kill()
        child.wait()
    with path.open("w") as fh:
        oscompat.lock(fh, blocking=False)


def test_pid_alive():
    assert oscompat.pid_alive(os.getpid())
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not oscompat.pid_alive(child.pid)
    assert not oscompat.pid_alive(0)


def test_prepare_windows_app_is_a_no_op_elsewhere(monkeypatch):
    if oscompat.WINDOWS:
        pytest.skip("Windows: covered by the installer test in CI")
    path = os.environ.get("PATH")
    oscompat.prepare_windows_app()
    assert os.environ.get("PATH") == path and not getattr(subprocess.Popen, "_verbatim_no_window", False)


@pytest.mark.skipif(not oscompat.WINDOWS, reason="Windows only")
def test_prepare_windows_app_finds_bundled_ffmpeg(tmp_path, monkeypatch):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "verbatim" / ".venv"))
    monkeypatch.setenv("PATH", "C:\\other")
    oscompat.prepare_windows_app()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tmp_path / "bin")
    assert subprocess.run([sys.executable, "-c", "pass"]).returncode == 0  # still starts processes
