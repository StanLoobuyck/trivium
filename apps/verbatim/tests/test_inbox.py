"""Watch folder (inbox.py): which slides go with a recording, when it's ready, queueing without duplicates."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lecture import inbox, webapp
from lecture import queue as q
from lecture.config import load_config, load_courses


@pytest.mark.parametrize("stem,n", [
    ("DEP les 4 - Aula 2026-02-26 16 - 05", 4), ("HC03_slides", 3), ("Lecture 12 handout", 12),
    ("week_7", 7), ("Slides202627_Part2_color", None), ("Les 3, part 1", 3), ("lessen overzicht", None),
])
def test_lecture_number(stem, n):
    assert inbox.lecture_number(stem) == n


@pytest.mark.parametrize("stem,covers", [
    ("Les 4", {4}), ("Deel 2 (Les 3-6)", {3, 4, 5, 6}), ("HC 03 - 05", {3, 4, 5}), ("les 2 t/m 4", {2, 3, 4}),
    ("Les 3–4", {3, 4}), ("Slides Hoofdstuk 3", set()), ("les 4 - 16 - 05", {4}), ("Les 5-3", {5}),
    ("Les 3-2026", {3}),
])
def test_deck_lectures(stem, covers):
    assert inbox.deck_lectures(stem) == covers


def test_one_deck_serves_several_lectures():
    span = [Path("Deel 2 (Les 3-6).pdf"), Path("Les 7.pdf")]
    assert inbox.pick_slides(Path("Les 5.mp4"), span) == ([span[0]], "lecture 5")
    assert inbox.pick_slides(Path("DEP les 7.mp4"), span) == ([span[1]], "lecture 7")


def test_missing_deck_waits_then_takes_all():
    decks = [Path("Les 1.pdf"), Path("Les 2.pdf")]
    assert inbox.pick_slides(Path("Les 3.mp4"), decks, inbox.MISSING_DECK_WAIT_S - 1)[0] is None
    assert inbox.pick_slides(Path("Les 3.mp4"), decks, inbox.MISSING_DECK_WAIT_S) == (decks, "all decks of the course")


def test_pick_slides():
    v = Path("DEP les 4 - Aula.mp4")
    big = [Path("Slides_Part1.pdf"), Path("Slides_Part2.pdf")]
    assert inbox.pick_slides(v, big) == (big, "all decks of the course")
    per_lecture = [Path("les 3.pdf"), Path("les 4.pdf"), Path("les 4 extra.pptx")]
    assert inbox.pick_slides(v, per_lecture) == ([Path("les 4 extra.pptx"), Path("les 4.pdf")], "lecture 4")
    slides, why = inbox.pick_slides(Path("DEP les 5.mp4"), per_lecture)
    assert slides is None and "lecture 5" in why             # its deck isn't on the shelf yet: wait
    assert inbox.pick_slides(Path("random.mp4"), per_lecture) == (sorted(per_lecture), "all decks of the course")
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


def test_moved_old_recording_still_gets_its_full_wait(box, monkeypatch):
    conf, root, queue, tick = box
    monkeypatch.setattr(q, "Queue", lambda: queue)
    dep = root / "digitale-elektronica"
    put(dep / "les 1.pdf", 3600)
    put(dep / "les 3.mp4", 90 * 24 * 3600)                  # old mtime, as after moving a file in
    (f,) = inbox.scan(conf, load_courses())
    assert not f["ready"] and "30 min" in f["why"]
    (f,) = inbox.scan(conf, load_courses(), now=time.time() + inbox.MISSING_DECK_WAIT_S)
    assert f["ready"] and [Path(s).name for s in f["slides"]] == ["les 1.pdf"]


def test_start_without_slides_skips_the_wait(box, monkeypatch):
    """Owner's request 2026-11-12: Start without slides on a lecture that waits for its deck (10 or 30 min)."""
    conf, root, queue, tick = box
    monkeypatch.setattr(q, "Queue", lambda: queue)
    dep = root / "digitale-elektronica"
    put(dep / "les 1.pdf", 3600)
    put(dep / "les 3.mp4", 120)                               # numbered decks, none for lecture 3: waits 30 min
    put(root / "algemene-economie" / "week 2.mp4", 120)       # empty shelf: waits 10 min
    put(dep / "les 1.mp4", 5)                                 # has its deck, still downloading: no button
    found = {Path(f["media"]).name: f for f in inbox.scan(conf, load_courses())}
    assert found["les 3.mp4"]["slides_wait"] and found["week 2.mp4"]["slides_wait"]
    assert not found["les 1.mp4"]["slides_wait"]

    client = TestClient(webapp.create_app(), base_url="http://127.0.0.1")
    W = {"x-lecture-ui": "1"}
    assert client.post("/api/inbox/start", json={"media": found["les 1.mp4"]["media"]}, headers=W).status_code == 404
    for name in ("les 3.mp4", "week 2.mp4"):
        assert client.post("/api/inbox/start", json={"media": found[name]["media"]}, headers=W).status_code == 200
    added = tick(queue, conf)
    assert sorted((i["title"], i["slides"]) for i in added) == [("Les 3", []), ("Week 2", [])]
    assert inbox.no_slides(conf) == set()                    # forgotten once queued


# --- simple mode: Velox folders become courses -------------------------------------------------------------

import httpx  # noqa: E402

from lecture import settings  # noqa: E402

PAGE = "<html><head><title>Inleiding tot het recht | KU Leuven | Onderwijsaanbod</title></head></html>"


class Catalogue:
    def __init__(self, pages=None, offline=False):
        self.pages, self.offline, self.asked = pages or {}, offline, []

    def get(self, url, timeout, follow_redirects):
        self.asked.append(url)
        if self.offline:
            raise httpx.ConnectError("no network")
        code = url.rsplit("/", 1)[1].removesuffix("N.htm")
        return httpx.Response(200, text=self.pages[code]) if code in self.pages else httpx.Response(500, text="")


@pytest.fixture
def simple_box(xdg, tmp_path, no_inbox):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(
        f"app:\n  simple: true\npaths:\n  jobs_dir: {tmp_path / 'jobs'}\n  inbox_dir: {tmp_path / 'inbox'}\n"
        f"  downloads_inbox: {tmp_path / 'dl'}\n")
    return load_config(), tmp_path / "dl", q.Queue(tmp_path / "queue.json"), no_inbox


def test_catalogue_name():
    assert inbox.catalogue_name("C00A1A", Catalogue({"C00A1A": PAGE})) == "Inleiding tot het recht"
    assert inbox.catalogue_name("C99Z9Z", Catalogue()) is None


def test_velox_folder_becomes_a_course(simple_box):
    conf, dl, _, _ = simple_box
    put(dl / "C00A1A" / "Hoorcollege 1.mp4", 120)
    put(dl / "C00B2B" / "Les 2.mp4", 120)              # no catalogue page: named after the code
    (dl / "C00C3C").mkdir()                             # no recording yet: not a course
    (dl / "notes").mkdir()                              # not a course code
    put(dl / "notes" / "x.mp4", 120)
    cat = Catalogue({"C00A1A": PAGE})
    new = inbox.adopt_new_codes(conf, load_courses(), cat)
    assert [(c.name, c.codes, c.id) for c in new] == [
        ("Inleiding tot het recht", ["C00A1A"], "inleiding-tot-het-recht"), ("C00B2B", ["C00B2B"], "c00b2b")]
    assert inbox.adopt_new_codes(conf, load_courses(), cat) == [] and len(cat.asked) == 2  # once only


def test_offline_tries_again_later(simple_box):
    conf, dl, _, _ = simple_box
    put(dl / "C00A1A" / "Hoorcollege 1.mp4", 120)
    assert inbox.adopt_new_codes(conf, load_courses(), Catalogue(offline=True)) == []
    assert inbox.adopt_new_codes(conf, load_courses(), Catalogue({"C00A1A": PAGE}))[0].name == "Inleiding tot het recht"


def test_same_name_gets_its_own_id(simple_box):
    conf, dl, _, _ = simple_box
    settings.save_course({"id": "inleiding-tot-het-recht", "name": "Inleiding tot het recht", "language": "nl"})
    put(dl / "C00A1A" / "Hoorcollege 1.mp4", 120)
    new = inbox.adopt_new_codes(conf, load_courses(), Catalogue({"C00A1A": PAGE}))
    assert new[0].id == "inleiding-tot-het-recht-c00a1a" and len(load_courses()) == 2


def test_tick_queues_velox_download_with_notes_when_gemini_is_set(simple_box, monkeypatch):
    conf, dl, queue, tick = simple_box
    monkeypatch.setattr(q, "Queue", lambda: queue)
    monkeypatch.setattr(inbox, "catalogue_name", lambda code, client=None: "Inleiding tot het recht")
    monkeypatch.setattr(inbox, "EMPTY_SHELF_WAIT_S", 0)
    monkeypatch.setattr(settings, "claude_login", lambda: {"installed": False, "logged_in": None})  # this laptop has it
    put(dl / "C00A1A" / "Hoorcollege 1.mp4", 120)
    added = tick(queue, conf)
    assert [(i["course"], i["notes"]) for i in added] == [("inleiding-tot-het-recht", "never")]  # no Gemini key
    settings.set_key("gemini", "AIza" + "b" * 35)
    put(dl / "C00A1A" / "Hoorcollege 2.mp4", 120)
    assert [i["notes"] for i in tick(queue, conf)] == ["now"]
    settings.update_settings({"app": {"auto_notes": False}})
    put(dl / "C00A1A" / "Hoorcollege 3.mp4", 120)
    assert [i["notes"] for i in tick(queue, load_config())] == ["never"]


def test_deleting_a_lecture_from_a_course_folder_starts_it_over(box, monkeypatch):
    """A friend's laptop (2026-11-13): Velox recording run without slides, lecture deleted, and the next round queued it
    straight back without slides. Now the wait for slides starts again from the delete."""
    import json

    from lecture.api import common

    conf, root, queue, tick = box
    monkeypatch.setattr(q, "Queue", lambda: queue)
    monkeypatch.setattr(common, "Queue", lambda: queue)
    dep = root / "digitale-elektronica"
    video = put(dep / "les 2.mp4", 0)
    later = time.time() + 2 * 3600                            # two hours after it landed: its wait is long over
    monkeypatch.setattr(inbox.time, "time", lambda: later)
    (added,) = tick(queue, conf)
    assert added["slides"] == []                              # forgot the slides
    queue.forget(added["id"])
    job = conf.paths.jobs_dir / "2026-11-13_digitale-elektronica_les-2"
    job.mkdir(parents=True)
    (job / "manifest.json").write_text(json.dumps({"title": "Les 2", "input": {"media": str(video)}}))

    client = TestClient(webapp.create_app(), base_url="http://127.0.0.1")
    r = client.delete(f"/api/lectures/{job.name}", headers={"x-lecture-ui": "1"})
    assert r.status_code == 200 and Path(r.json()["waits_for_slides"]) == dep
    assert video.exists() and not job.exists()
    assert tick(queue, conf) == []                            # doesn't come straight back
    (f,) = inbox.scan(conf, load_courses())
    assert not f["ready"] and f["slides_wait"] and "10 min" in f["why"]

    put(dep / "les 2.pdf", 0)                                 # the slides arrive
    (again,) = tick(queue, conf)
    assert [Path(s).name for s in again["slides"]] == ["les 2.pdf"]
    assert inbox.restarted(conf) == {}                        # forgotten once queued


def test_restart_only_for_recordings_in_a_course_folder(box):
    conf, root, queue, tick = box
    elsewhere = put(root.parent / "Videos" / "les 2.mp4", 3600)
    upload = put(root / "uploads" / "les 3.mp4", 3600)
    assert inbox.restart(conf, elsewhere) is None and inbox.restart(conf, upload) is None
    assert inbox.restart(conf, root / "digitale-elektronica" / "gone.mp4") is None
    assert inbox.restarted(conf) == {}
