"""Watch folder (inbox.py): which slides go with a recording, when it's ready, queueing without duplicates."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from lecture import inbox
from lecture import queue as q
from lecture.config import load_config, load_courses


@pytest.mark.parametrize("stem,n", [
    ("DEP les 4 - Aula 2026-02-26 16 - 05", 4), ("HC03_slides", 3), ("Lecture 12 handout", 12),
    ("week_7", 7), ("Slides202627_Part2_color", None), ("Les 3, part 1", 3), ("lessen overzicht", None),
])
def test_lecture_number(stem, n):
    assert inbox.lecture_number(stem) == n


def test_pick_slides():
    v = Path("DEP les 4 - Aula.mp4")
    big = [Path("Slides_Part1.pdf"), Path("Slides_Part2.pdf")]
    assert inbox.pick_slides(v, big) == (big, "all decks of the course")
    per_lecture = [Path("les 3.pdf"), Path("les 4.pdf"), Path("les 4 extra.pptx")]
    assert inbox.pick_slides(v, per_lecture) == ([Path("les 4 extra.pptx"), Path("les 4.pdf")], "lecture 4")
    slides, why = inbox.pick_slides(Path("DEP les 5.mp4"), per_lecture)
    assert slides is None and "lecture 5" in why             # its deck isn't on the shelf yet: wait
    assert inbox.pick_slides(Path("random.mp4"), per_lecture)[0] is None
    assert inbox.pick_slides(Path("x.mp4"), [Path("x.pdf"), *big]) == ([Path("x.pdf")], "same name")
    assert inbox.pick_slides(v, []) == ([], "no slides")


@pytest.fixture
def box(xdg, tmp_path, no_inbox):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {tmp_path / 'jobs'}\n  inbox_dir: {tmp_path / 'inbox'}\n")
    conf = load_config()
    return conf, tmp_path / "inbox", q.Queue(tmp_path / "queue.json"), no_inbox


def put(path: Path, age_s: float, data: bytes = b"x" * 10) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - age_s
    os.utime(path, (t, t))
    return path


def test_tick_queues_ready_recordings_once(box, monkeypatch):
    conf, root, queue, tick = box
    monkeypatch.setattr(q, "Queue", lambda: queue)        # known_media() looks at this queue
    dep = root / "digitale-elektronica"
    put(dep / "Slides_Part1.pdf", 3600)
    put(dep / "Slides_Part2.pdf", 3600)
    put(dep / "DEP les 4 - Aula 2026-02-26.mp4", 120)
    put(dep / "DEP les 5.mp4", 5)                          # still downloading
    put(root / "uploads" / "les 9.mp4", 120)               # browser uploads: not a course
    put(root / "not-a-course" / "les 1.mp4", 120)

    added = tick(queue, conf)
    assert [(i["title"], i["date"], i["notes"]) for i in added] == [("Les 4", "2026-02-26", "never")]
    assert [Path(s).name for s in added[0]["slides"]] == ["Slides_Part1.pdf", "Slides_Part2.pdf"]
    found = {Path(f["media"]).name: f for f in inbox.scan(conf, load_courses())}
    assert "DEP les 4 - Aula 2026-02-26.mp4" not in found     # already queued
    assert not found["DEP les 5.mp4"]["ready"] and "copied" in found["DEP les 5.mp4"]["why"]
    assert tick(queue, conf) == []
    assert (root / "algemene-economie").is_dir()             # folders made for the courses


def test_empty_shelf_waits_then_goes_without_slides(box, monkeypatch):
    conf, root, queue, tick = box
    monkeypatch.setattr(q, "Queue", lambda: queue)
    put(root / "digitale-elektronica" / "les 2.mp4", 120)
    (f,) = inbox.scan(conf, load_courses())
    assert not f["ready"] and "10 min" in f["why"]
    (f,) = inbox.scan(conf, load_courses(), now=time.time() + inbox.EMPTY_SHELF_WAIT_S)
    assert f["ready"] and f["slides"] == []
