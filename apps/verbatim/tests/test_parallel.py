"""Two lectures at once (transcribe.parallel_lectures), but the laptop GPU / Groq one lecture at a time."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from lecture import config as cfg
from lecture import pipeline
from lecture import queue as qmod
from lecture.report import NullReporter


def test_worker_runs_two_lectures_side_by_side(xdg, tmp_path, monkeypatch):
    conf = cfg.load_config()
    assert conf.transcribe.parallel_lectures == 2
    q = qmod.Queue(tmp_path / "queue.json")
    for name in ("les1", "les2", "les3"):
        (tmp_path / f"{name}.mp4").write_bytes(b"x")
        q.add(tmp_path / f"{name}.mp4", "dep", notes="never")
    running, peak, seen = [0], [0], []
    lock = threading.Lock()

    def fake_transcribe(queue, item, conf):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.3)
        with lock:
            running[0] -= 1
            seen.append(Path(item["media"]).stem)
        queue.update(item["id"], status="done")

    monkeypatch.setattr(qmod, "transcribe_item", fake_transcribe)
    qmod.work(conf, q, once=True, sleep=lambda s: None)
    assert peak[0] == 2 and sorted(seen) == ["les1", "les2", "les3"]
    assert all(i["status"] == "done" for i in q.snapshot()["items"])


def test_laptop_gpu_is_used_by_one_lecture_at_a_time(xdg, monkeypatch):
    from lecture.providers import local_whisper

    loaded = []

    class FakeLocal:
        name = "local"

        def __init__(self, conf, reporter=None):
            pass

        def check(self):
            loaded.append(time.monotonic())

        def close(self):
            pass

    monkeypatch.setattr(local_whisper, "LocalWhisper", FakeLocal)
    conf = cfg.load_config()
    first = pipeline._local(conf, NullReporter())
    got = []
    t = threading.Thread(target=lambda: got.append(pipeline._local(conf, NullReporter())))
    t.start()
    time.sleep(0.2)
    assert not got and len(loaded) == 1   # the second lecture waits; no second model on the GPU
    pipeline._close(first)
    t.join(2)
    assert got and len(loaded) == 2
    pipeline._close(got[0])
    assert pipeline._EXCLUSIVE["local"].acquire(blocking=False)  # released again
    pipeline._EXCLUSIVE["local"].release()


def test_a_failed_model_load_releases_the_gpu(xdg, monkeypatch):
    from lecture.providers import local_whisper

    class Broken:
        def __init__(self, conf, reporter=None):
            pass

        def check(self):
            raise local_whisper.LocalUnavailable("no CUDA")

    monkeypatch.setattr(local_whisper, "LocalWhisper", Broken)
    try:
        pipeline._local(cfg.load_config(), NullReporter())
    except local_whisper.LocalUnavailable:
        pass
    assert pipeline._EXCLUSIVE["local"].acquire(blocking=False)
    pipeline._EXCLUSIVE["local"].release()
