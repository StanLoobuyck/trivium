"""The few things that differ between Linux, macOS and Windows: file locks, "is this process alive",
opening a file or URL with the desktop, and starting a process that outlives its parent.

Everything else in Verbatim is plain pathlib/subprocess and works the same everywhere.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import IO, Any

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"

if WINDOWS:
    import msvcrt
else:
    import fcntl


def lock(fh: IO[Any], blocking: bool = True) -> None:
    """Exclusive lock on an open file, released by `unlock` or by closing it.

    Non-blocking and already held elsewhere → BlockingIOError (like fcntl.flock with LOCK_NB).
    """
    if not WINDOWS:
        fcntl.flock(fh, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return
    # msvcrt locks a byte range per handle; byte 0 is enough (it may lie past the end of an empty file).
    # LK_LOCK gives up after 10 s, so blocking means retrying the non-blocking lock.
    while True:
        fh.seek(0)
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            if not blocking:
                raise BlockingIOError(f"{getattr(fh, 'name', 'file')} is locked") from None
            time.sleep(0.05)


def unlock(fh: IO[Any]) -> None:
    if not WINDOWS:
        fcntl.flock(fh, fcntl.LOCK_UN)
        return
    fh.seek(0)
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if WINDOWS:
        # os.kill(pid, 0) on Windows sends Ctrl+C (signal 0 == CTRL_C_EVENT): ask the kernel instead.
        import ctypes

        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists
        try:
            code = ctypes.c_ulong()
            return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def detached() -> dict[str, Any]:
    """Popen keyword arguments for a child that keeps running when its parent exits, without a console window."""
    if WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def no_window() -> dict[str, Any]:
    """Popen/run keyword arguments that keep a console window from flashing up for a helper (ffmpeg) on Windows."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}


def open_with_desktop(target: str) -> None:
    """Open a folder, file or URL the way a double-click would."""
    if WINDOWS:
        os.startfile(target)  # noqa: S606 — what Explorer does on a double-click
        return
    subprocess.Popen(["open" if MACOS else "xdg-open", target], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, **detached())
