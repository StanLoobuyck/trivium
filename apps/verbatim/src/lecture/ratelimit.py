"""Persistent rolling-window quota ledger, shared by every lecture process via flock.

The ledger is an estimate (other apps on the same Groq org aren't counted); a server 429 always
wins. Usage is reserved *before* a call and released if the call fails, so concurrent processes
never both think the same budget is free.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import oscompat
from .report import NullReporter, Reporter
from .util import read_json, write_json

DAY_S = 24 * 3600


@dataclass(frozen=True)
class Window:
    name: str        # human readable, e.g. "hourly audio"
    seconds: float   # rolling window length
    limit: float
    field: str       # "requests" or "audio_s"


class QuotaExhausted(Exception):
    def __init__(self, window: str, resume_at: datetime):
        super().__init__(f"{window} limit reached; continue after {resume_at:%a %H:%M}")
        self.window = window
        self.resume_at = resume_at


def groq_stt_windows(limits) -> list[Window]:
    return [
        Window("requests/min", 60, limits.requests_per_minute, "requests"),
        Window("requests/day", DAY_S, limits.requests_per_day, "requests"),
        Window("hourly audio", 3600, limits.audio_seconds_per_hour, "audio_s"),
        Window("daily audio", DAY_S, limits.audio_seconds_per_day, "audio_s"),
    ]


class Ledger:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep):
        self.path = path
        self.lock_path = path.with_suffix(".lock")
        self.clock = clock
        self.sleep = sleep

    @contextmanager
    def _locked(self) -> Iterator[list[dict]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("w") as lock:
            oscompat.lock(lock)
            try:
                events = read_json(self.path)["events"] if self.path.exists() else []
                horizon = self.clock() - DAY_S
                events = [e for e in events if e["t"] > horizon]
                yield events
                write_json(self.path, {"events": events})
            finally:
                oscompat.unlock(lock)

    def _wait_needed(self, events: list[dict], bucket: str, windows: list[Window],
                     amounts: dict[str, float]) -> tuple[float, Window | None]:
        """Seconds until all windows have room for `amounts`, and the window that needs the longest wait."""
        now = self.clock()
        worst, worst_window = 0.0, None
        for w in windows:
            amount = amounts.get(w.field, 0.0)
            if amount > w.limit:
                raise ValueError(f"a single call needs {amount} {w.field}, more than the {w.name} limit {w.limit}")
            inside = sorted((e for e in events if e["bucket"] == bucket and e["t"] > now - w.seconds),
                            key=lambda e: e["t"])
            excess = sum(e.get(w.field, 0.0) for e in inside) + amount - w.limit
            if excess <= 0:
                continue
            freed = 0.0
            for e in inside:  # oldest events leave the window first
                freed += e.get(w.field, 0.0)
                if freed >= excess:
                    wait = e["t"] + w.seconds - now
                    if wait > worst:
                        worst, worst_window = wait, w
                    break
        return worst, worst_window

    def reserve(self, bucket: str, windows: list[Window], amounts: dict[str, float],
                max_wait_s: float, reporter: Reporter | None = None, label: str = "") -> str:
        """Block until the budget allows the call, record it, return its event id.

        Raises QuotaExhausted instead of waiting longer than max_wait_s.
        """
        reporter = reporter or NullReporter()
        while True:
            with self._locked() as events:
                wait, window = self._wait_needed(events, bucket, windows, amounts)
                if wait <= 0:
                    event_id = uuid.uuid4().hex[:12]
                    events.append({"id": event_id, "t": self.clock(), "bucket": bucket, **amounts})
                    return event_id
            resume_at = datetime.fromtimestamp(self.clock() + wait)
            if wait > max_wait_s:
                raise QuotaExhausted(f"{label} {window.name}".strip(), resume_at)
            if wait > 5:
                reporter.info(f"{label} {window.name} limit reached — continuing automatically at "
                              f"{resume_at:%H:%M}".strip())
            self.sleep(wait + 1.0)

    def release(self, event_id: str) -> None:
        """Undo a reservation whose call failed before the provider counted it."""
        with self._locked() as events:
            events[:] = [e for e in events if e["id"] != event_id]

    def usage(self, bucket: str, windows: list[Window]) -> dict[str, tuple[float, float]]:
        """{window name: (used, limit)} for display."""
        now = self.clock()
        with self._locked() as events:
            return {
                w.name: (sum(e.get(w.field, 0.0) for e in events
                             if e["bucket"] == bucket and e["t"] > now - w.seconds), w.limit)
                for w in windows
            }


def resume_time_text(resume_at: datetime) -> str:
    today = datetime.now().date()
    day = "today" if resume_at.date() == today else (
        "tomorrow" if resume_at.date() == today + timedelta(days=1) else f"{resume_at:%a %d %b}")
    return f"{day} at {resume_at:%H:%M}"
