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


def job_dir(root, media="Les 3 (2026-10-01).mp4", course="digitale-elektronica", name="2026-10-01_x", notes=False):
    folder = root / "jobs" / name
    (folder / "outputs").mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({
        "course": course, "title": "Les 3", "date": "2026-10-01", "input": {"media": f"/x/{media}"}}))
    (folder / "outputs" / "transcript.md").write_text("x")
    if notes:
        (folder / "outputs" / "notes.md").write_text("x")
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


def capture(monkeypatch):
    sent = []
    def post(url, json, headers, timeout):
        sent.append((url, json, headers))
        return httpx.Response(200, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    return sent


def test_finished_lectures_are_reported_once_with_the_file_name(linked, monkeypatch):
    with_code()
    sent = capture(monkeypatch)
    job_dir(linked, notes=True)
    assert hub.report() == 2
    url, event, headers = sent[-1]
    assert url == "https://hub.example/api/events" and headers["Authorization"].startswith("Bearer ")
    assert event["type"] == "notes.ready" and event["payload"]["kind"] == "notes"
    assert event["payload"]["verbatimJob"] == "2026-10-01_x"
    assert event["payload"]["recording"] == {
        "courseCode": "H06F2a", "title": "Les 3", "recordedOn": "2026-10-01",
        "fileName": "Les 3 (2026-10-01).mp4", "lectureNumber": 3}
    assert hub.report() == 0 and len(sent) == 2


def test_notes_made_later_are_reported_too(linked, monkeypatch):
    with_code()
    sent = capture(monkeypatch)
    folder = job_dir(linked)
    hub.report()
    (folder / "outputs" / "notes.md").write_text("x")
    assert hub.report() == 1 and sent[-1][1]["payload"]["kind"] == "notes"


def test_a_guessed_date_is_not_passed_on(linked, monkeypatch):
    with_code()
    sent = capture(monkeypatch)
    job_dir(linked, media="DEP Les11, part3 - 2024.mp4")
    hub.report()
    recording = sent[0][1]["payload"]["recording"]
    assert "recordedOn" not in recording and recording["lectureNumber"] == 3


def test_what_could_not_be_delivered_goes_out_later_with_the_same_id(linked, monkeypatch):
    with_code()
    job_dir(linked)
    def down(*args, **kwargs):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr(httpx, "post", down)
    assert hub.report() == 0
    sent = capture(monkeypatch)
    assert hub.report() == 1
    assert sent[0][1]["id"] == hub.notes_event(json.loads((linked / "jobs/2026-10-01_x/manifest.json").read_text()),
                                               "2026-10-01_x", "transcript", next(c for c in cfg.load_courses() if c.codes))["id"]


def test_a_link_made_after_the_worker_started_is_seen(xdg, tmp_path, monkeypatch):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {tmp_path / 'jobs'}\n  inbox_dir: {tmp_path / 'in'}\n")
    (tmp_path / "jobs").mkdir()
    started_with = cfg.load_config()
    assert started_with.hub.url == ""
    with_code()
    job_dir(tmp_path)
    settings.set_hub_url("https://hub.example")
    monkeypatch.setenv("LECTURE_HUB_CODE", "x" * 40)
    sent = capture(monkeypatch)
    hub.report_quietly()
    assert len(sent) == 1


def test_alone_nothing_happens(xdg, tmp_path, monkeypatch):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {tmp_path}\n  inbox_dir: {tmp_path}\n")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("no hub configured"))
    assert hub.report() == 0


@pytest.mark.parametrize("name,n", [
    ("Religie, zingeving en levensbeschouwing - RZL Ingenieurswetenschappen 5 - 2026 (2026-10-19)", 5),
    ("RZL Ingenieurswetenschappen 3 ", 3), ("Lessen 12", 12),
    ("EBS - Aula 200L 00.06 2026-09-22 10 - 37", None), ("Slides202627_Part2", None),
    ("Digitale signaalverwerking 2026", None), ("Hoofdstuk 0", None),
])
def test_trailing_number(name, n):
    assert hub.trailing_number(name) == n
