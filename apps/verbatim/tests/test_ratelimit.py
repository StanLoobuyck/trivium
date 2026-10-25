import threading

import pytest

from lecture.ratelimit import Ledger, QuotaExhausted, Window

WINDOWS = [Window("requests/min", 60, 3, "requests"), Window("hourly audio", 3600, 1000, "audio_s")]


class FakeClock:
    def __init__(self):
        self.t = 1_000_000.0
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def ledger(tmp_path, clock):
    return Ledger(tmp_path / "ledger.json", clock=clock, sleep=clock.sleep)


def test_request_window_waits_for_oldest_event(tmp_path):
    clock = FakeClock()
    lg = ledger(tmp_path, clock)
    for _ in range(3):
        lg.reserve("b", WINDOWS, {"requests": 1, "audio_s": 10}, max_wait_s=3600)
        clock.t += 5
    lg.reserve("b", WINDOWS, {"requests": 1, "audio_s": 10}, max_wait_s=3600)
    # oldest event at t0 leaves the 60 s window at t0+60; we were at t0+15 → waited 45 s (+1 s margin)
    assert clock.slept == [pytest.approx(46.0)]


def test_audio_window_and_quota_exhausted(tmp_path):
    clock = FakeClock()
    lg = ledger(tmp_path, clock)
    lg.reserve("b", WINDOWS, {"requests": 1, "audio_s": 600}, max_wait_s=100)
    clock.t += 61
    with pytest.raises(QuotaExhausted) as exc:
        lg.reserve("b", WINDOWS, {"requests": 1, "audio_s": 600}, max_wait_s=100)
    assert exc.value.window == "hourly audio"
    assert exc.value.resume_at.timestamp() == pytest.approx(1_000_000 + 3600)


def test_release_frees_budget_and_buckets_are_separate(tmp_path):
    clock = FakeClock()
    lg = ledger(tmp_path, clock)
    ev = lg.reserve("b", WINDOWS, {"requests": 1, "audio_s": 900}, max_wait_s=0)
    lg.reserve("other", WINDOWS, {"requests": 1, "audio_s": 900}, max_wait_s=0)
    lg.release(ev)
    lg.reserve("b", WINDOWS, {"requests": 1, "audio_s": 900}, max_wait_s=0)  # would raise without release
    assert lg.usage("b", WINDOWS)["hourly audio"] == (900, 1000)


def test_single_call_larger_than_limit_is_an_error(tmp_path):
    lg = ledger(tmp_path, FakeClock())
    with pytest.raises(ValueError):
        lg.reserve("b", WINDOWS, {"requests": 1, "audio_s": 2000}, max_wait_s=0)


def test_concurrent_processes_never_overbook(tmp_path):
    """Separate Ledger objects (like separate processes) share the file under flock."""
    windows = [Window("requests/min", 60, 20, "requests")]
    ok, refused = [], []

    def worker():
        lg = Ledger(tmp_path / "ledger.json")
        for _ in range(10):
            try:
                lg.reserve("b", windows, {"requests": 1}, max_wait_s=0)
                ok.append(1)
            except QuotaExhausted:
                refused.append(1)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ok) == 20 and len(refused) == 20
