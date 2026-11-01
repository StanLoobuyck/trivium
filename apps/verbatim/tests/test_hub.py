"""The optional link with Inhaal's hub. No network: httpx is replaced."""

import json

import httpx
import pytest

from lecture import config as cfg
from lecture import hub, inbox, settings


@pytest.fixture
def linked(xdg, tmp_path, monkeypatch):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(
        f"paths:\n  jobs_dir: {tmp_path / 'jobs'}\n  inbox_dir: {tmp_path / 'inbox'}\n"
        f"  downloads_inbox: {tmp_path / 'dl'}\nhub:\n  url: https://hub.example\n")
    (tmp_path / "jobs").mkdir()
    monkeypatch.setenv("LECTURE_HUB_CODE", "x" * 40)
    return tmp_path


def job_dir(root, media="Les 3 (2026-10-01).mp4", course="digitale-elektronica"):
    folder = root / "jobs" / "2026-10-01_x"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps({
        "course": course, "title": "Les 3", "date": "2026-10-01", "input": {"media": f"/x/{media}"}}))
    return folder


def with_code(code="H06F2a"):
    settings.save_course({**cfg.load_courses()[2].model_dump(), "codes": [code]})


def test_download_folder_finds_the_course_by_code_in_any_case(linked):
    with_code()
    folder = linked / "dl" / "H06F2A"
    folder.mkdir(parents=True)
    (folder / "les.mp4").write_bytes(b"x")
    (linked / "dl" / "ONBEKEND").mkdir()
    (linked / "dl" / "ONBEKEND" / "les.mp4").write_bytes(b"x")
    conf = cfg.load_config()
    found = inbox.scan(conf, cfg.load_courses(), now=1e12)
    assert [(f["course"], f["ready"]) for f in found] == [("digitale-elektronica", True)]


def test_import_links_by_name_and_code_and_adds_the_rest(linked):
    before = {c.id: c for c in cfg.load_courses()}
    result = settings.import_courses([
        {"name": "Digitale Elektronica en Processoren", "codes": ["H01L1a"], "language": "nl"},
        {"name": "Semiconductor Physics", "codes": ["H06F2a", "H06F3a"], "language": "en"},
    ])
    assert result == {"linked": 1, "added": 1}
    courses = {c.id: c for c in cfg.load_courses()}
    linked_course = courses["digitale-elektronica"]
    assert linked_course.codes == ["H01L1a"]
    assert linked_course.lecturer == before["digitale-elektronica"].lecturer
    assert courses["semiconductor-physics"].language == "en"
    assert settings.import_courses([{"name": "Andere naam", "codes": ["h06f2A"]}]) == {"linked": 1, "added": 0}
    assert len(cfg.load_courses()) == len(courses)


def test_course_save_keeps_codes(linked):
    with_code()
    course = next(c for c in cfg.load_courses() if c.id == "digitale-elektronica")
    assert course.codes == ["H06F2a"]


def test_notes_ready_is_sent_with_the_file_name(linked, monkeypatch):
    with_code()
    sent = []
    def post(url, json, headers, timeout):
        sent.append((url, json, headers))
        return httpx.Response(200, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    hub.tell_notes_ready(job_dir(linked), "notes", cfg.load_config())
    url, event, headers = sent[0]
    assert url == "https://hub.example/api/events" and headers["Authorization"].startswith("Bearer ")
    assert event["type"] == "notes.ready" and event["payload"]["kind"] == "notes"
    assert event["payload"]["verbatimJob"] == "2026-10-01_x"
    assert event["payload"]["recording"] == {
        "courseCode": "H06F2a", "title": "Les 3", "recordedOn": "2026-10-01",
        "fileName": "Les 3 (2026-10-01).mp4", "lectureNumber": 3}


def test_undelivered_message_waits_and_goes_later(linked, monkeypatch):
    with_code()
    def down(*args, **kwargs):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr(httpx, "post", down)
    conf = cfg.load_config()
    hub.tell_notes_ready(job_dir(linked), "transcript", conf)
    outbox = linked / "jobs" / "hub_outbox.json"
    assert len(json.loads(outbox.read_text())) == 1
    sent = []
    monkeypatch.setattr(httpx, "post", lambda url, json, headers, timeout: (
        sent.append(json), httpx.Response(200, request=httpx.Request("POST", url)))[1])
    hub.flush(conf)
    assert len(sent) == 1 and json.loads(outbox.read_text()) == []


def test_alone_nothing_happens(xdg, tmp_path, monkeypatch):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {tmp_path}\n  inbox_dir: {tmp_path}\n")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("no hub configured"))
    hub.tell_notes_ready(tmp_path, "notes", cfg.load_config())
    assert not (tmp_path / "hub_outbox.json").exists()
