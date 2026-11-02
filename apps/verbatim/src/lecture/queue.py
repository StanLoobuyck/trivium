"""Machine-wide lecture queue (file-locked JSON) and the worker that empties it.

One worker at a time (worker lock). It transcribes one lecture at a time on the GPU (stages 1–8) and makes
notes when the item's policy allows: "now", "tonight" (notes.tonight window) or "never". Notes waiting for
budget/login never block transcription: the worker transcribes the next lecture meanwhile. Items survive
restarts: anything left "transcribing"/"notes" by a dead worker goes back to the queue and resumes (every
stage resumes from its saved work).

Status flow: queued → transcribing → transcribed → notes → done
                                   ↘ done (notes: never)   ↘ notes_pending (waits; resume_at) → notes
             any step → failed (retry puts it back where it failed)
"""

from __future__ import annotations

import fcntl
import shutil
import os
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import config as cfgmod
from .config import Config
from . import hub
from .notify import notify
from .providers.claude_cli import schedule_allows
from .util import read_json, write_json

NOTES_POLICIES = ("now", "tonight", "never")
ACTIVE = ("transcribing", "notes", "latex")


class Stopped(BaseException):
    """The user stopped this item (UI: Stop). A BaseException, like Ctrl+C, so the providers' fallbacks
    (`except Exception`: try the next model) can't swallow it."""


def queue_path() -> Path:
    return cfgmod.cache_dir() / "queue.json"


class Queue:
    def __init__(self, path: Path | None = None, clock: Callable[[], datetime] = datetime.now):
        self.path = path or queue_path()
        self.clock = clock

    @contextmanager
    def _locked(self) -> Iterator[dict[str, Any]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                state = read_json(self.path) if self.path.exists() else {"items": [], "notes_paused": False}
                yield state
                write_json(self.path, state)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def snapshot(self) -> dict[str, Any]:
        with self._locked() as state:
            return {"items": [dict(i) for i in state["items"]], "notes_paused": state["notes_paused"]}

    def add(self, media: Path, course: str, slides: list[Path] | None = None, title: str | None = None,
            date: str | None = None, notes: str = "now", language: str | None = None) -> dict[str, Any]:
        if notes not in NOTES_POLICIES:
            raise ValueError(f"notes must be one of {', '.join(NOTES_POLICIES)}")
        media = media.expanduser().resolve()
        if not media.is_file():
            raise FileNotFoundError(media)
        item = {"id": uuid.uuid4().hex[:8], "media": str(media), "course": course,
                "slides": [str(Path(s).expanduser().resolve()) for s in slides or []],
                "title": title, "date": date, "notes": notes, "language": language, "status": "queued",
                "added": self.clock().isoformat(timespec="seconds"), "job": None, "stage": None,
                "progress": None, "message": None, "error": None, "resume_at": None}
        with self._locked() as state:
            state["items"].append(item)
        return item

    def add_notes(self, job_root: Path, media: str, course: str, notes: str = "now") -> dict[str, Any]:
        """(Re)make the notes of an already transcribed job: the item starts at "transcribed"."""
        with self._locked() as state:
            for item in state["items"]:
                if item.get("job") == str(job_root) and item["status"] in ("transcribed", "notes", "notes_pending"):
                    return dict(item)  # already waiting for notes
            item = {"id": uuid.uuid4().hex[:8], "media": media, "course": course, "slides": [], "title": None,
                    "date": None, "notes": notes, "status": "transcribed", "added": self.clock().isoformat(timespec="seconds"),
                    "job": str(job_root), "stage": None, "progress": None, "message": "notes requested",
                    "error": None, "resume_at": None}
            state["items"].append(item)
            return dict(item)

    def add_latex(self, job_root: Path, media: str, course: str) -> dict[str, Any]:
        """Queue the LaTeX notes of a finished lecture (latex.py)."""
        with self._locked() as state:
            for item in state["items"]:
                if item.get("job") == str(job_root) and item["status"] in ("latex_queued", "latex"):
                    return dict(item)
            item = {"id": uuid.uuid4().hex[:8], "media": media, "course": course, "slides": [], "title": None,
                    "date": None, "notes": "never", "status": "latex_queued", "kind": "latex",
                    "added": self.clock().isoformat(timespec="seconds"), "job": str(job_root), "stage": None,
                    "progress": None, "message": "LaTeX requested", "error": None, "resume_at": None}
            state["items"].append(item)
            return dict(item)

    def update(self, item_id: str, **fields: Any) -> None:
        with self._locked() as state:
            for item in state["items"]:
                if item["id"] == item_id:
                    item.update(fields)
                    return
        raise KeyError(item_id)

    def set_notes_paused(self, paused: bool) -> None:
        with self._locked() as state:
            state["notes_paused"] = paused

    def retry(self, item_id: str) -> None:
        """A failed item goes back to where it failed: transcription, or notes when the transcript is done."""
        with self._locked() as state:
            for item in state["items"]:
                if item["id"] == item_id and item["status"] in ("failed", "notes_pending"):
                    back = {"notes": "transcribed", "latex": "latex_queued"}.get(item.get("failed_at"), "queued")
                    item.update(status=back, error=None, resume_at=None)
                    return
        raise KeyError(f"{item_id}: no failed or pending item with this id")

    def request_stop(self, item_id: str) -> None:
        """Ask the worker to stop an item it is working on; it stops at its next progress step."""
        with self._locked() as state:
            for item in state["items"]:
                if item["id"] == item_id and item["status"] in ACTIVE:
                    item["stop"] = True
                    return
        raise KeyError(f"{item_id}: not being worked on right now")

    def stop_requested(self, item_id: str) -> bool:
        return any(i["id"] == item_id and i.get("stop") for i in self.snapshot()["items"])

    def forget(self, item_id: str) -> None:
        """Drop an item whatever its status (after the worker stopped it)."""
        with self._locked() as state:
            state["items"] = [i for i in state["items"] if i["id"] != item_id]

    def remove(self, item_id: str) -> None:
        with self._locked() as state:
            before = len(state["items"])
            state["items"] = [i for i in state["items"] if not (i["id"] == item_id and i["status"] not in ACTIVE)]
            if len(state["items"]) == before:
                raise KeyError(f"{item_id}: unknown, or being worked on right now")

    def forget_job(self, job: Path) -> None:
        """Drop every item of a lecture that is being deleted; refuses while the worker is on it."""
        with self._locked() as state:
            mine = [i for i in state["items"] if i.get("job") and Path(i["job"]).name == job.name]
            if any(i["status"] in ACTIVE for i in mine):
                raise KeyError(f"{job.name}: being worked on right now")
            state["items"] = [i for i in state["items"] if i not in mine]

    def retitle(self, job: Path, title: str) -> None:
        """A lecture was renamed: its queue items show the new title. Refuses while the worker is on it (the
        worker rewrites the manifest after every stage and would undo the rename)."""
        with self._locked() as state:
            mine = [i for i in state["items"] if i.get("job") and Path(i["job"]).name == job.name]
            if any(i["status"] in ACTIVE for i in mine):
                raise KeyError(f"{job.name}: being worked on right now")
            for i in mine:
                i["title"] = title

    def clear_done(self) -> int:
        """Forget finished items (their lectures stay in the library)."""
        with self._locked() as state:
            before = len(state["items"])
            state["items"] = [i for i in state["items"] if i["status"] != "done"]
            return before - len(state["items"])

    def recover(self, alive: Callable[[int], bool]) -> list[str]:
        """Items a dead worker left active go back to the queue (their work resumes)."""
        back = []
        with self._locked() as state:
            for item in state["items"]:
                if item["status"] in ACTIVE and not alive(item.get("pid") or -1):
                    item["status"] = {"transcribing": "queued", "latex": "latex_queued"}.get(item["status"], "transcribed")
                    back.append(item["id"])
        return back

    def _due(self, item: dict) -> bool:
        return not item.get("resume_at") or datetime.fromisoformat(item["resume_at"]) <= self.clock()

    def claim_transcription(self, pid: int) -> dict | None:
        with self._locked() as state:
            for item in state["items"]:  # oldest first
                if item["status"] == "queued" and self._due(item):
                    item.update(status="transcribing", pid=pid, error=None, resume_at=None, stop=False,
                                started_at=self.clock().isoformat(timespec="seconds"))
                    return dict(item)
        return None

    def claim_notes(self, pid: int, conf: Config) -> dict | None:
        with self._locked() as state:
            if state["notes_paused"]:
                return None
            for item in state["items"]:
                if item["status"] not in ("transcribed", "notes_pending") or not self._due(item):
                    continue
                if item["notes"] == "tonight" and not schedule_allows(conf.notes.tonight, self.clock())[0]:
                    continue
                item.update(status="notes", pid=pid, error=None, resume_at=None, stop=False,
                            started_at=self.clock().isoformat(timespec="seconds"))
                return dict(item)
        return None

    def claim_latex(self, pid: int) -> dict | None:
        with self._locked() as state:
            for item in state["items"]:
                if item["status"] == "latex_queued" and self._due(item):
                    item.update(status="latex", pid=pid, error=None, resume_at=None, stop=False,
                                started_at=self.clock().isoformat(timespec="seconds"))
                    return dict(item)
        return None

    def next_notes_time(self, conf: Config) -> datetime | None:
        """When the earliest waiting notes item may run (for status display)."""
        times = []
        for item in self.snapshot()["items"]:
            if item["status"] in ("transcribed", "notes_pending"):
                t = datetime.fromisoformat(item["resume_at"]) if item.get("resume_at") else self.clock()
                if item["notes"] == "tonight":
                    ok, start = schedule_allows(conf.notes.tonight, t)
                    t = t if ok else start
                times.append(t)
        return min(times) if times else None


class QueueReporter:
    """Writes the current stage/progress of an item into the queue (throttled), for `queue list` and the UI."""

    def __init__(self, queue: Queue, item_id: str, min_interval_s: float = 2.0):
        self.queue, self.item_id, self.min_interval_s = queue, item_id, min_interval_s
        self._last = 0.0

    def _check_stop(self) -> None:
        if self.queue.stop_requested(self.item_id):
            raise Stopped(self.item_id)

    def stage(self, name: str) -> None:
        self._check_stop()
        self.queue.update(self.item_id, stage=name, progress=None)

    def progress(self, done: float, total: float, text: str = "") -> None:
        now = time.monotonic()
        if now - self._last >= self.min_interval_s:
            self._last = now
            self._check_stop()
            self.queue.update(self.item_id, progress=round(done / total, 3) if total else None, message=text)

    def info(self, message: str) -> None:
        self._check_stop()
        self.queue.update(self.item_id, message=message)
        print(f"[{self.item_id}] {message}", flush=True)

    def warn(self, message: str) -> None:
        self.queue.update(self.item_id, message=f"⚠ {message}")
        print(f"[{self.item_id}] WARNING {message}", flush=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class WorkerRunning(RuntimeError):
    pass


@contextmanager
def worker_lock() -> Iterator[None]:
    path = cfgmod.cache_dir() / "worker.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise WorkerRunning("a lecture worker is already running") from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def worker_running() -> bool:
    try:
        with worker_lock():
            return False
    except WorkerRunning:
        return True


def _title(item: dict) -> str:
    return item.get("title") or Path(item["media"]).stem


def transcribe_item(queue: Queue, item: dict, conf: Config) -> None:
    from . import pipeline
    from .ratelimit import QuotaExhausted

    rep = QueueReporter(queue, item["id"])
    try:
        job, _, _ = pipeline.open_job(conf, Path(item["media"]), item["course"], [Path(s) for s in item["slides"]],
                                      item["title"], item["date"], language=item.get("language"))
        queue.update(item["id"], job=str(job.root))
        pipeline.run_job(job, conf, rep)
    except QuotaExhausted as exc:  # Groq fallback hit its daily cap: wait, don't fail
        queue.update(item["id"], status="queued", resume_at=exc.resume_at.isoformat(timespec="minutes"),
                     message=str(exc))
        return
    except Stopped:
        stopped_transcription(queue, item, conf)
        return
    except KeyboardInterrupt:
        queue.update(item["id"], status="queued", message="interrupted; resumes on the next worker start")
        raise
    except Exception as exc:  # noqa: BLE001 — recorded on the item; the worker goes on with the next one
        queue.update(item["id"], status="failed", failed_at="transcription", error=f"{type(exc).__name__}: {exc}")
        notify("Lecture failed", f"{_title(item)}: {exc}", urgency="critical")
        return
    try:
        suggestions(job.root, conf, rep)
    except Stopped:
        stopped_transcription(queue, item, conf)
        return
    if item["notes"] == "never":
        queue.update(item["id"], status="done", stage=None, progress=None)
        notify("Lecture transcribed", _title(item))
        hub.report_quietly()
    else:
        queue.update(item["id"], status="transcribed", stage=None, progress=None,
                     message="transcribed; notes " + ("tonight" if item["notes"] == "tonight" else "next"))
        notify("Lecture transcribed", f"{_title(item)} — notes {'tonight' if item['notes'] == 'tonight' else 'next'}")


def stopped_transcription(queue: Queue, item: dict, conf: Config) -> None:
    """Stopped by the user: what was done goes, and the inbox won't pick the recording up again by itself."""
    from . import inbox

    job = next((i.get("job") for i in queue.snapshot()["items"] if i["id"] == item["id"]), None)
    if job and Path(job).is_dir() and Path(job).resolve().parent == conf.paths.jobs_dir.resolve():
        shutil.rmtree(job, ignore_errors=True)
    inbox.ignore(conf, Path(item["media"]))
    queue.forget(item["id"])
    print(f"[{item['id']}] stopped by the user; progress removed", flush=True)


def _remove_newer(folder: Path, since: str | None, pattern: str) -> None:
    """Files of this run only: the ones written since it started (earlier runs' results stay)."""
    if not since or not folder.is_dir():
        return
    start = datetime.fromisoformat(since).timestamp()
    for f in folder.glob(pattern):
        if f.stat().st_mtime >= start:
            f.unlink(missing_ok=True)


def suggestions(job_root: Path, conf: Config, rep: QueueReporter) -> None:
    """Term fix suggestions on the Mac right after transcription; never fails the lecture."""
    from . import pipeline
    from .job import Job
    from .providers.mac_whisper import MacUnavailable

    if not conf.termfix.enabled:
        return
    try:
        pipeline.run_termfix(Job(job_root), conf, rep)
    except MacUnavailable as exc:
        rep.info(f"term suggestions skipped: {exc}")
    except Exception as exc:  # noqa: BLE001 — recorded in termfix.json; the transcript is fine
        rep.warn(f"term suggestions failed: {type(exc).__name__}: {exc}")


def notes_item(queue: Queue, item: dict, conf: Config) -> None:
    from . import pipeline
    from .job import Job
    from .stages.s7_notes import NotesPending

    rep = QueueReporter(queue, item["id"])
    try:
        pipeline.run_notes(Job(Path(item["job"])), conf, rep)
    except NotesPending as exc:
        resume = exc.resume_at or (queue.clock() + timedelta(hours=1))
        first = item.get("status") != "notes_pending" and not item.get("pending_notified")
        queue.update(item["id"], status="notes_pending", resume_at=resume.isoformat(timespec="minutes"),
                     message=str(exc)[:300], pending_notified=True)
        if first:
            notify("Lecture notes waiting", f"{_title(item)}: {str(exc)[:150]}")
        return
    except Stopped:
        _remove_newer(Path(item["job"]) / "notes", item.get("started_at"), "batch_*.json")
        queue.forget(item["id"])
        print(f"[{item['id']}] notes stopped by the user; this run's parts removed", flush=True)
        return
    except KeyboardInterrupt:
        queue.update(item["id"], status="transcribed", message="interrupted; notes resume on the next worker start")
        raise
    except Exception as exc:  # noqa: BLE001
        queue.update(item["id"], status="failed", failed_at="notes", error=f"{type(exc).__name__}: {exc}")
        notify("Lecture notes failed", f"{_title(item)}: {exc}", urgency="critical")
        return
    queue.update(item["id"], status="done", stage=None, progress=None, message="notes ready")
    notify("Lecture notes ready", _title(item))
    hub.report_quietly()


def latex_item(queue: Queue, item: dict, conf: Config) -> None:
    from . import latex
    from .providers.llm import LLMLimit

    try:
        latex.run(Path(item["job"]), conf, QueueReporter(queue, item["id"]))
    except LLMLimit as exc:
        resume = exc.resume_at or (queue.clock() + timedelta(hours=1))
        queue.update(item["id"], status="latex_queued", resume_at=resume.isoformat(timespec="minutes"),
                     stage=None, message=str(exc)[:300])
        return
    except Stopped:
        queue.forget(item["id"])
        print(f"[{item['id']}] LaTeX notes stopped by the user", flush=True)
        return
    except KeyboardInterrupt:
        queue.update(item["id"], status="latex_queued", stage=None, message="interrupted; resumes on the next worker start")
        raise
    except Exception as exc:  # noqa: BLE001
        queue.update(item["id"], status="failed", failed_at="latex", stage=None, error=f"{type(exc).__name__}: {exc}")
        notify("LaTeX notes failed", f"{_title(item)}: {exc}", urgency="critical")
        return
    queue.update(item["id"], status="done", stage=None, progress=None, message="LaTeX notes ready")
    notify("LaTeX notes ready", _title(item))


def watch_inbox(queue: Queue, conf: Config) -> bool:
    """Queue new recordings from ~/Lectures/inbox/<course>/ (inbox.py); True when something was added."""
    from . import inbox

    hub.report_quietly()
    try:
        added = inbox.tick(queue, conf, lambda msg: print(msg, flush=True))
    except Exception as exc:  # noqa: BLE001 — a bad file in the inbox must not stop the worker
        print(f"inbox: {type(exc).__name__}: {exc}", flush=True)
        return False
    for item in added:
        notify("Lecture queued from the inbox", _title(item))
    return bool(added)


def _loop(queue: Queue, conf: Config, pid: int, once: bool, idle_s: float, sleep: Callable[[float], None],
          notes_lock: threading.Lock) -> None:
    while True:
        item = queue.claim_transcription(pid)
        if item:
            transcribe_item(queue, item, conf)
            continue
        if notes_lock.acquire(blocking=False):  # notes one at a time (Claude/Gemini limits)
            try:
                item = queue.claim_notes(pid, conf)
                if item:
                    notes_item(queue, item, conf)
                else:
                    item = queue.claim_latex(pid)
                    if item:
                        latex_item(queue, item, conf)
            finally:
                notes_lock.release()
            if item:
                continue
        if watch_inbox(queue, conf):
            continue
        if once:
            return
        sleep(idle_s)


def work(conf: Config, queue: Queue | None = None, once: bool = False, idle_s: float = 30.0,
         sleep: Callable[[float], None] = time.sleep) -> None:
    """Worker loop. Transcription first (oldest first), notes when nothing is waiting for the GPU.
    transcribe.parallel_lectures > 1: that many loops side by side (claims are file-locked; the laptop GPU and
    Groq are still used by one lecture at a time, see pipeline._EXCLUSIVE).
    once=True: process until nothing is runnable now, then return (tests, `lecture worker --once`)."""
    queue = queue or Queue()
    pid = os.getpid()
    notes_lock = threading.Lock()
    with worker_lock():
        for item_id in queue.recover(_pid_alive):
            print(f"[{item_id}] resumed after an interrupted worker", flush=True)
        n = conf.transcribe.parallel_lectures
        if n <= 1:
            return _loop(queue, conf, pid, once, idle_s, sleep, notes_lock)
        threads = [threading.Thread(target=_loop, args=(queue, conf, pid, once, idle_s, sleep, notes_lock),
                                    name=f"lectures-{i + 1}", daemon=True) for i in range(n)]
        for th in threads:
            th.start()
        for th in threads:  # daemon threads: Ctrl+C / systemctl stop ends them; items resume on restart
            th.join()
