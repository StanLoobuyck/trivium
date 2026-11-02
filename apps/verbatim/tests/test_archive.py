"""Semesters + archive (media copies to the Mac and back). The "Mac" is a local folder here: no ssh."""

from __future__ import annotations

import json
from datetime import date

import pytest

from lecture import archive
from lecture.config import Course
from lecture.semesters import current_semester, is_archived, overview, semester_of


def test_semester_names_follow_the_academic_year():
    assert semester_of("2026-09-23") == "2026-27 S1"
    assert semester_of("2027-01-20") == "2026-27 S1"   # January exams belong to S1
    assert semester_of("2026-02-26") == "2025-26 S2"
    assert semester_of("2026-08-25") == "2025-26 S2"   # August resits too
    assert current_semester(date(2026, 10, 20)) == "2026-27 S1"
    assert "2025-26 S2" < "2026-27 S1" < "2026-27 S2"  # names sort by time


def test_past_courses_are_archived_unless_kept():
    c = lambda **kw: Course(id="dep", name="DEP", language="nl", notes_language="nl", **kw)  # noqa: E731
    today = date(2026, 10, 20)
    assert is_archived(c(), "2025-26 S2", today) and not is_archived(c(), "2026-27 S1", today)
    assert not is_archived(c(archived=False), "2025-26 S2", today)   # "Move back to current"
    assert is_archived(c(archived=True), "2026-27 S1", today)        # "Archive this semester"
    ov = overview([c(), Course(id="dsp", name="DSP", language="nl", notes_language="nl")],
                  [{"course": "dep", "date": "2026-03-05"}, {"course": "dsp", "date": "2026-09-23"}], today)
    assert ov["courses"]["dep"] == {"semester": "2025-26 S2", "archived": True, "explicit": False}
    assert list(ov["semesters"]) == ["2026-27 S1", "2025-26 S2"]


@pytest.fixture
def job(xdg, tmp_path):
    inbox = tmp_path / "inbox"
    (inbox / "uploads").mkdir(parents=True)
    xdg.mkdir(parents=True, exist_ok=True)
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {tmp_path / 'jobs'}\n  inbox_dir: {inbox}\n")
    root = tmp_path / "jobs" / "2026-03-05_dep_les-6"
    (root / "media").mkdir(parents=True)
    (root / "audio").mkdir()
    upload = inbox / "uploads" / "les 6.mp4"
    upload.write_bytes(b"original upload" * 1000)
    (root / "media" / "player.mp4").write_bytes(b"player copy" * 1000)
    (root / "audio" / "full.flac").write_bytes(b"flac" * 1000)
    (root / "outputs").mkdir()
    (root / "outputs" / "transcript.md").write_text("stays")
    (root / "manifest.json").write_text(json.dumps({"version": 1, "input": {"media": str(upload)}, "stages": {}}))
    return root, upload


def test_move_verifies_then_frees_space_and_restore_brings_it_back(job, tmp_path):
    root, upload = job
    remote = tmp_path / "mac-archive"
    assert [r for r, _ in archive.media_files(root)] == ["player.mp4", "full.flac", "upload/les 6.mp4"]
    out = archive.move_to_remote(root, str(remote))
    assert out["moved"] == 3 and out["bytes"] == 11000 + 4000 + 15000
    assert not (root / "media" / "player.mp4").exists() and not upload.exists()
    assert (root / "outputs" / "transcript.md").read_text() == "stays"
    assert (remote / root.name / "upload" / "les 6.mp4").read_bytes() == b"original upload" * 1000
    st = archive.status(root)
    assert st["on_mac"] and st["local_bytes"] == 0
    assert archive.restore(root)["restored"] == 3
    assert upload.read_bytes() == b"original upload" * 1000 and not archive.status(root)["on_mac"]
    assert (remote / root.name / "full.flac").exists()  # the remote copy stays as a backup


def test_a_bad_copy_deletes_nothing(job, tmp_path, monkeypatch):
    root, upload = job
    monkeypatch.setattr(archive, "_remote_sha256", lambda remote, rel: "0" * 64)
    with pytest.raises(archive.ArchiveError, match="nothing deleted"):
        archive.move_to_remote(root, str(tmp_path / "mac-archive"))
    assert (root / "media" / "player.mp4").exists() and upload.exists()
    assert "archive" not in json.loads((root / "manifest.json").read_text())


def test_originals_outside_uploads_are_never_moved(job, tmp_path):
    root, _ = job
    original = tmp_path / "Videos" / "Recordings" / "les 6.mp4"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"mine")
    m = json.loads((root / "manifest.json").read_text())
    m["input"]["media"] = str(original)
    (root / "manifest.json").write_text(json.dumps(m))
    archive.move_to_remote(root, str(tmp_path / "mac-archive"))
    assert original.read_bytes() == b"mine"


def test_semesters_api_and_move_back(job, monkeypatch):
    from fastapi.testclient import TestClient

    from lecture import semesters, settings, webapp

    root, _ = job
    m = json.loads((root / "manifest.json").read_text())
    m.update(course="dep", date="2026-03-05", title="Les 6")
    (root / "manifest.json").write_text(json.dumps(m))
    settings.save_course({"id": "dep", "name": "DEP", "language": "nl"})
    monkeypatch.setattr(semesters, "date", type("D", (), {"today": staticmethod(lambda: date(2026, 10, 20)),
                                                           "fromisoformat": staticmethod(date.fromisoformat)}))
    client = TestClient(webapp.create_app(), base_url="http://127.0.0.1")
    sem = client.get("/api/semesters").json()
    assert sem["current"] == "2026-27 S1" and sem["courses"]["dep"]["archived"] is True
    past = next(s for s in sem["semesters"] if s["name"] == "2025-26 S2")
    assert past["archived"] and past["local_bytes"] == 30000
    r = client.post("/api/courses/dep/archived", json={"archived": False}, headers={"x-lecture-ui": "1"})
    assert r.status_code == 200
    assert client.get("/api/semesters").json()["courses"]["dep"] == {"semester": "2025-26 S2", "archived": False,
                                                                      "explicit": True}


def test_a_chosen_semester_decides_again(xdg):
    from lecture import config as cfg
    from lecture import settings

    settings.save_course({"id": "dep", "name": "DEP", "language": "nl", "archived": False})
    dep = lambda: next(x for x in cfg.load_courses() if x.id == "dep")  # noqa: E731
    settings.save_course({**dep().model_dump(), "semester": "2026-27 S1", "archived": None})
    c = dep()
    assert (c.semester, c.archived) == ("2026-27 S1", None)
    ov = overview([c], [{"course": "dep", "date": "2026-03-05"}], date(2026, 10, 20))
    assert ov["courses"]["dep"] == {"semester": "2026-27 S1", "archived": False, "explicit": False}
    with pytest.raises(Exception):
        settings.save_course({**c.model_dump(), "semester": "2026 S1"})  # not a semester name


def test_course_saves_through_the_api_keep_semester_and_archived(xdg):
    from fastapi.testclient import TestClient

    from lecture import config as cfg
    from lecture import webapp

    client = TestClient(webapp.create_app(), base_url="http://127.0.0.1")
    w = {"x-lecture-ui": "1"}
    r = client.post("/api/courses", json={"id": "dep", "name": "DEP", "language": "nl", "semester": "2026-27 S1"}, headers=w)
    assert r.status_code == 200
    dep = lambda: next(x for x in cfg.load_courses() if x.id == "dep")  # noqa: E731
    assert dep().semester == "2026-27 S1"
    client.post("/api/courses/dep/archived", json={"archived": True}, headers=w)
    # what the page sends for a rename or a word fix: the course as /api/courses returned it, one field changed
    course = next(c for c in client.get("/api/courses").json() if c["id"] == "dep")
    client.post("/api/courses", json={**course, "corrections": {"Carnot-kaart": "Karnaugh-kaart"}}, headers=w)
    assert (dep().semester, dep().archived, dep().corrections) == ("2026-27 S1", True, {"Carnot-kaart": "Karnaugh-kaart"})
    client.post("/api/courses", json={**course, "notes_without_slides": True}, headers=w)
    assert dep().notes_without_slides is True and dep().semester == "2026-27 S1"
