"""Machine-wide queue + worker (pipeline replaced by fakes: no GPU, no LLM)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from lecture import pipeline
from lecture import queue as q
from lecture.config import load_config
from lecture.ratelimit import QuotaExhausted
from lecture.stages.s7_notes import NotesPending


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(xdg, tmp_path, monkeypatch):
    conf = load_config()
    clock = Clock(datetime(2026, 10, 17, 14, 0))
    queue = q.Queue(tmp_path / "queue.json", clock=clock)
    media = []
    for i in range(3):
        m = tmp_path / f"les{i}.mp4"
        m.write_bytes(b"x")
        media.append(m)
    calls = []
    monkeypatch.setattr(q, "notify", lambda *a, **k: calls.append(("notify", a[0])))

    class FakeJob:
        def __init__(self, root):
            self.root = Path(root)

    def open_job(conf, media, course, slides, title, date, new=False, language=None):
        return FakeJob(tmp_path / "jobs" / media.stem), True, []

    monkeypatch.setattr(pipeline, "open_job", open_job)
    import lecture.job
    monkeypatch.setattr(lecture.job, "Job", FakeJob)  # the notes step reopens the job from its folder
    monkeypatch.setattr(pipeline, "run_job", lambda job, conf, rep: calls.append(("transcribe", job.root.name)))
    monkeypatch.setattr(pipeline, "run_notes", lambda job, conf, rep: calls.append(("notes", job.root.name)))
    return conf, queue, clock, media, calls


def _statuses(queue):
    return [i["status"] for i in queue.snapshot()["items"]]


def test_worker_transcribes_all_before_notes_and_respects_policies(env):
    conf, queue, clock, media, calls = env
    queue.add(media[0], "dep", notes="now")
    queue.add(media[1], "dep", notes="tonight")
    queue.add(media[2], "dep", notes="never")
    q.work(conf, queue, once=True)
    work = [c for c in calls if c[0] != "notify"]
    assert work == [("transcribe", "les0"), ("transcribe", "les1"), ("transcribe", "les2"), ("notes", "les0")]
    assert _statuses(queue) == ["done", "transcribed", "done"]  # les1 waits for tonight
    clock.t = datetime(2026, 10, 17, 23, 0)
    q.work(conf, queue, once=True)
    assert calls[-2:] == [("notes", "les1"), ("notify", "Lecture notes ready")]
    assert _statuses(queue) == ["done", "done", "done"]


def test_paused_notes_wait_but_transcription_goes_on(env):
    conf, queue, clock, media, calls = env
    queue.set_notes_paused(True)
    queue.add(media[0], "dep")
    q.work(conf, queue, once=True)
    assert _statuses(queue) == ["transcribed"]
    queue.set_notes_paused(False)
    q.work(conf, queue, once=True)
    assert _statuses(queue) == ["done"]


def test_notes_pending_retries_later_and_doesnt_block_next_lecture(env, monkeypatch):
    conf, queue, clock, media, calls = env
    later = clock.t + timedelta(hours=3)

    def pending(job, conf, rep):
        raise NotesPending(["claude: usage limit"], later)

    monkeypatch.setattr(pipeline, "run_notes", pending)
    queue.add(media[0], "dep")
    q.work(conf, queue, once=True)
    queue.add(media[1], "dep", notes="never")
    q.work(conf, queue, once=True)
    items = queue.snapshot()["items"]
    assert [i["status"] for i in items] == ["notes_pending", "done"]
    assert items[0]["resume_at"] == later.isoformat(timespec="minutes")
    assert sum(c == ("notify", "Lecture notes waiting") for c in calls) == 1  # notified once, not every retry
    assert queue.next_notes_time(conf) == later


def test_quota_waits_and_failures_are_recorded_then_retried(env, monkeypatch):
    conf, queue, clock, media, calls = env
    resume = clock.t + timedelta(hours=2)

    def quota(job, conf, rep):
        raise QuotaExhausted("Groq daily audio", resume)

    monkeypatch.setattr(pipeline, "run_job", quota)
    item = queue.add(media[0], "dep")
    q.work(conf, queue, once=True)
    assert _statuses(queue) == ["queued"]  # waiting, not failed: not claimed before resume_at
    assert queue.claim_transcription(1) is None

    def boom(job, conf, rep):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pipeline, "run_job", boom)
    clock.t = resume
    q.work(conf, queue, once=True)
    failed = queue.snapshot()["items"][0]
    assert failed["status"] == "failed" and "disk full" in failed["error"]
    queue.retry(item["id"])
    assert _statuses(queue) == ["queued"]


def test_failed_notes_retry_skips_transcription(env, monkeypatch):
    conf, queue, clock, media, calls = env
    monkeypatch.setattr(pipeline, "run_notes", lambda *a: (_ for _ in ()).throw(RuntimeError("bad")))
    item = queue.add(media[0], "dep")
    q.work(conf, queue, once=True)
    queue.retry(item["id"])
    assert _statuses(queue) == ["transcribed"]


def test_items_of_a_dead_worker_resume(env):
    conf, queue, clock, media, calls = env
    queue.add(media[0], "dep")
    queue.claim_transcription(pid=999_999_999)  # a worker that no longer exists
    assert queue.recover(q._pid_alive) and _statuses(queue) == ["queued"]


def test_only_one_worker(env):
    with q.worker_lock():
        assert q.worker_running()
        with pytest.raises(q.WorkerRunning):
            with q.worker_lock():
                pass
    assert not q.worker_running()


def test_add_checks_input(env):
    conf, queue, clock, media, calls = env
    with pytest.raises(FileNotFoundError):
        queue.add(Path("/nope.mp4"), "dep")
    with pytest.raises(ValueError):
        queue.add(media[0], "dep", notes="sometime")


def test_clear_done_keeps_unfinished(env):
    conf, queue, clock, media, calls = env
    queue.add(media[0], "dep", notes="never")
    q.work(conf, queue, once=True)
    queue.add(media[1], "dep")
    assert queue.clear_done() == 1 and _statuses(queue) == ["queued"]
