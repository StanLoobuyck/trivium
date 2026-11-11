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
