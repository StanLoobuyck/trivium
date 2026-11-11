"""Web app API (FastAPI TestClient; no browser, no worker)."""

import json

import pytest
from fastapi.testclient import TestClient

from lecture import queue as q
from lecture import webapp
from lecture import naming
from lecture.api import common

W = {"x-lecture-ui": "1"}


@pytest.fixture
def env(xdg, tmp_path, monkeypatch):
    xdg.mkdir(parents=True)
    jobs = tmp_path / "jobs"
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {jobs}\n  inbox_dir: {tmp_path / 'inbox'}\n")
    queue = q.Queue(tmp_path / "queue.json")
    monkeypatch.setattr(common, "Queue", lambda: queue)
    monkeypatch.setattr(common, "worker_running", lambda: True)
    monkeypatch.setattr(webapp.Path, "home", staticmethod(lambda: tmp_path / "home"))
    video = tmp_path / "home" / "Videos" / "Recordings" / "DEP les 4 - Aula 2026-02-26 16 - 05.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"0123456789" * 100)
    # one finished job (transcript + sections, no notes)
    job = jobs / "2026-02-26_digitale-elektronica_les-4"
    (job / "outputs").mkdir(parents=True)
    (job / "manifest.json").write_text(json.dumps({
        "title": "Les 4", "date": "2026-02-26", "course": "digitale-elektronica", "input": {"media": str(video)},
        "stages": {"audio": {"duration_s": 7100}, "sections": {"status": "done", "sections": 2}}}))
    (job / "transcript_raw.json").write_text(json.dumps({"segments": [{"start": 1.0, "end": 3.0, "text": " Hallo"}]}))
    (job / "sections.json").write_text(json.dumps({"method": "slides", "sections": [
        {"index": 1, "title": "NAND", "start": 0, "end": 60, "slides": [], "low_confidence": False}],
        "slides_not_discussed": []}))
    (job / "outputs" / "review.md").write_text("# Review\n- ok")
    return TestClient(webapp.create_app(), base_url="http://127.0.0.1"), queue, video, job


@pytest.mark.parametrize("stem,title,date", [
    ("Digitale elektronica en processoren - DEP les 4 - Aula B Celestijnenlaan 200C 2026-02-26 16 - 05", "Les 4", "2026-02-26"),
    ("Digitale elektronica en processoren - DEP Les 3, part 1 - februari 22ste 2023, 5 - 17 - 55 pm", "Les 3 deel 1", "2023-02-22"),
    ("Lecture 7 - October 3rd, 2026", "Lecture 7", "2026-10-03"),
    ("random_recording", "random recording", None),
])
def test_guess_title_and_date(stem, title, date):
    assert naming.guess_title(stem) == title
    if date:
        assert naming.guess_date(stem, 0) == date


def test_guess_course_needs_two_name_words(xdg):
    from lecture.config import load_courses

    courses = load_courses()
    assert naming.guess_course("Digitale elektronica en processoren - DEP les 4", courses) == "digitale-elektronica"
    assert naming.guess_course("les 4", courses) is None


def test_guard_rejects_foreign_hosts_and_headerless_writes(env):
    client, queue, video, job = env
    assert client.get("/api/courses").status_code == 200
    assert client.get("/api/courses", headers={"host": "evil.example"}).status_code == 403
    assert client.post("/api/notes-paused", json={"paused": True}).status_code == 403  # no header: CSRF
    assert client.post("/api/notes-paused", json={"paused": True}, headers=W).status_code == 200


def test_add_validates_and_queues(env):
    client, queue, video, job = env
    bad = client.post("/api/queue", headers=W, json=[{"media": "/nope.mp4", "course": "x", "date": "26/02"}])
    assert bad.status_code == 400 and "not found" in bad.json()["detail"] and "choose a course" in bad.json()["detail"]
    assert client.post("/api/queue", headers=W, json=[{"media": str(video), "course": "digitale-elektronica",
                                                        "language": "fr"}]).status_code == 400
    ok = client.post("/api/queue", headers=W, json=[{"media": str(video), "course": "digitale-elektronica",
                                                       "title": "Les 4", "date": "2026-02-26", "notes": "tonight",
                                                       "language": "en"}])
    assert ok.status_code == 200 and queue.snapshot()["items"][0]["notes"] == "tonight"
    assert queue.snapshot()["items"][0]["language"] == "en"


def test_suggestions_skip_known_recordings(env):
    client, queue, video, job = env
    assert client.get("/api/suggestions").json()["videos"] == []  # the job already uses it
    other = video.parent / "Elektrische netten - les 2 - 2026-10-01.mp4"
    other.write_bytes(b"x")
    (v,) = client.get("/api/suggestions").json()["videos"]
    assert v["title"] == "Les 2" and v["date"] == "2026-10-01"


def test_library_and_lecture_detail(env):
    client, queue, video, job = env
    (lec,) = client.get("/api/lectures").json()
    assert lec["title"] == "Les 4" and lec["status"] == "transcribed" and not lec["has_notes"]
    d = client.get(f"/api/lectures/{job.name}").json()
    assert d["segments"][0]["text"] == "Hallo" and d["notes"] is None and d["media_available"]
    assert d["sections_detail"][0]["title"] == "NAND" and d["files"] == ["review.md"]
    assert d["terms"] == [] and d["whisper_prompt"] == ""
    (job / "terms.json").write_text(json.dumps({"whisper_prompt": "Les over NAND.", "terms": [
        {"term": "NAND", "slides": 5, "score": 10.0, "source": "slides"}]}))
    d = client.get(f"/api/lectures/{job.name}").json()
    assert d["terms"] == [{"term": "NAND", "source": "slides", "slides": 5}] and d["whisper_prompt"] == "Les over NAND."
    assert client.get("/api/lectures/..%2F..%2Fetc").status_code == 404


def test_files_only_from_outputs_and_media_seeks(env):
    client, queue, video, job = env
    assert client.get(f"/api/lectures/{job.name}/files/review.md").text.startswith("# Review")
    assert client.get(f"/api/lectures/{job.name}/files/..%2Fmanifest.json").status_code == 404
    r = client.get(f"/api/lectures/{job.name}/media", headers={"range": "bytes=10-19"})
    assert r.status_code == 206 and r.content == b"0123456789"


def test_subtitles_served_as_webvtt_for_the_player(env):
    client, queue, video, job = env
    assert client.get(f"/api/lectures/{job.name}").json()["subtitles"] is False
    assert client.get(f"/api/lectures/{job.name}/subtitles.vtt").status_code == 404
    (job / "outputs" / "subtitles.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nHallo\n")
    assert client.get(f"/api/lectures/{job.name}").json()["subtitles"] is True
    r = client.get(f"/api/lectures/{job.name}/subtitles.vtt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/vtt") and r.text.startswith("WEBVTT")
    assert "attachment" not in r.headers.get("content-disposition", "")


def test_make_notes_queues_once(env):
    client, queue, video, job = env
    for _ in range(2):
        assert client.post(f"/api/lectures/{job.name}/notes", headers=W).status_code == 200
    (item,) = queue.snapshot()["items"]
    assert item["status"] == "transcribed" and item["job"] == str(job)


def test_setup_reports_models_without_secrets_and_applies_changes(env, monkeypatch):
    from lecture import settings

    client, queue, video, job = env
    monkeypatch.setattr(settings, "claude_login", lambda: {"installed": True, "logged_in": True, "plan": "pro"})
    s = client.get("/api/setup").json()
    assert s["notes"]["label"] == "Claude Sonnet 5.5" and s["notes"]["detail"] == "claude_sub"
    assert s["outputs"] == {"exam_hints": False, "quiz": False, "flashcards": False, "glossary": False}
    assert "email" not in json.dumps(s) and set(s["keys"]) == {"groq", "gemini", "mac", "hub"}
    assert client.post("/api/setup/notes-model", headers=W, json={"value": "claude:claude-haiku-5-5"}).status_code == 200
    assert client.get("/api/setup").json()["notes"]["label"] == "Claude Haiku 5.5"
    assert client.post("/api/setup/stt", headers=W, json={"value": "nonsense"}).status_code == 400
    assert client.post("/api/setup/outputs", headers=W, json={"quiz": True}).status_code == 200
    assert client.get("/api/setup").json()["outputs"]["quiz"] is True
    assert client.get("/api/setup").json()["stt"]["skip_on_battery"] is True
    assert client.post("/api/setup/stt-battery", headers=W, json={"value": False}).status_code == 200
    assert client.get("/api/setup").json()["stt"]["skip_on_battery"] is False


def test_courses_and_folders_api(env):
    client, queue, video, job = env
    r = client.post("/api/courses", headers=W, json={"name": "Elektrische energie", "language": "nl",
                                                     "lecturer": "Jan Example", "extra_terms": ["HVDC"]})
    assert r.status_code == 200 and any(c["id"] == r.json()["id"] for c in client.get("/api/courses").json())
    assert client.delete(f"/api/courses/{r.json()['id']}").status_code == 403  # writes need the header
    assert client.delete(f"/api/courses/{r.json()['id']}", headers=W).status_code == 200
    f = client.post("/api/folders", headers=W, json={"folders": [{"id": "f1", "name": "Examen"}],
                                                       "assign": {job.name: "f1"}}).json()
    assert f["assign"] == {job.name: "f1"} and client.get("/api/folders").json() == f


def test_lecture_shows_which_models_made_it(env):
    client, queue, video, job = env
    m = json.loads((job / "manifest.json").read_text())
    m["stt"] = {"current_run": "r1", "runs": {"r1": {"provider": "local"}}}
    (job / "manifest.json").write_text(json.dumps(m))
    (job / "notes").mkdir()
    (job / "notes" / "batch_01.json").write_text(json.dumps({"provider": "claude:claude-sonnet-5-5",
                                                             "model": "claude-sonnet-5-5", "notes": {}}))
    (lec,) = client.get("/api/lectures").json()
    assert lec["models"] == {"stt": "Whisper large-v3 · your GPU", "notes": "Claude Sonnet 5.5"}


def test_upload_rejects_broken_files_and_skips_duplicates(env, tmp_path):
    client, queue, video, job = env
    r = client.post("/api/upload", headers=W, files={"file": ("RZL 1.mp4", b"")})
    assert r.status_code == 400 and "empty" in r.json()["detail"]
    r = client.post("/api/upload", headers=W, files={"file": ("RZL 1.mp4", b"not a video" * 100)})
    assert r.status_code == 400 and "can't read" in r.json()["detail"]
    first = client.post("/api/upload", headers=W, files={"file": ("les.pdf", b"%PDF-1.4 x")}).json()
    again = client.post("/api/upload", headers=W, files={"file": ("les.pdf", b"%PDF-1.4 x")}).json()
    assert again["path"] == first["path"]
    assert sorted(p.name for p in (tmp_path / "inbox" / "uploads").iterdir()) == ["les.pdf"]


def test_open_folder_falls_back_while_a_lecture_runs(env, monkeypatch):
    client, _, _, job = env
    opened = []
    monkeypatch.setattr("lecture.oscompat.open_with_desktop", opened.append)
    headers = {"x-lecture-ui": "1"}
    assert client.post(f"/api/lectures/{job.name}/open-folder", headers=headers).status_code == 200
    (job / "outputs" / "review.md").unlink()
    (job / "outputs").rmdir()
    assert client.post(f"/api/lectures/{job.name}/open-folder", headers=headers).status_code == 200
    assert opened == [str(job / "outputs"), str(job)]


def test_delete_lecture_removes_job_and_folder_entry(env):
    client, queue, video, job = env
    client.post("/api/folders", headers=W, json={"folders": [{"id": "f1", "name": "Examen"}],
                                                 "assign": {job.name: "f1"}})
    queue.add_notes(job, str(video), "digitale-elektronica")
    with queue._locked() as state:
        state["items"][0]["status"] = "notes"
    assert client.delete(f"/api/lectures/{job.name}", headers=W).status_code == 409  # worker busy on it
    with queue._locked() as state:
        state["items"][0]["status"] = "done"
    assert client.delete(f"/api/lectures/{job.name}", headers=W).status_code == 200
    assert not job.exists() and queue.snapshot()["items"] == []
    assert client.get("/api/folders").json()["assign"] == {}
    assert video.exists()  # the recording outside the app's upload folder stays


def test_rename_lecture_and_course(env):
    client, queue, video, job = env
    assert client.post(f"/api/lectures/{job.name}/rename", headers=W, json={"title": "  "}).status_code == 400
    r = client.post(f"/api/lectures/{job.name}/rename", headers=W, json={"title": " Les 4:  CMOS "})
    assert r.json()["title"] == "Les 4: CMOS"
    assert client.get(f"/api/lectures/{job.name}").json()["title"] == "Les 4: CMOS"
    (c,) = [c for c in client.get("/api/courses").json() if c["id"] == "digitale-elektronica"]
    c = {**c, "name": "DEP", "notes_language": "en"}
    assert client.post("/api/courses", headers=W, json=c).json()["id"] == "digitale-elektronica"
    (c2,) = [x for x in client.get("/api/courses").json() if x["id"] == "digitale-elektronica"]
    assert c2["name"] == "DEP" and c2["notes_language"] == "en" and c2["extra_terms"] == c["extra_terms"]


def test_term_suggestions_accept_course_and_run(env, monkeypatch):
    from lecture import pipeline, settings

    client, queue, video, job = env
    (job / "termfix.json").write_text(json.dumps({"status": "done", "model": "qwen3.8:27b", "answers": {"x": []},
        "suggestions": [{"id": "s1", "wrong": "nent", "right": "NAND", "start": 0, "end": 60, "at": 1.0,
                         "count": 1, "context": "een nent", "status": "open"}]}))
    refixes = []
    monkeypatch.setattr(pipeline, "refix", lambda job, conf, rep: refixes.append(job.root.name))
    d = client.get(f"/api/lectures/{job.name}").json()
    assert d["termfix"]["suggestions"][0]["wrong"] == "nent" and "answers" not in d["termfix"]

    r = client.post(f"/api/lectures/{job.name}/termfix/s1", json={"status": "rejected"}, headers=W)
    assert r.status_code == 200 and refixes == []          # nothing applied changed: no re-stitch
    client.post(f"/api/lectures/{job.name}/termfix/s1", json={"status": "accepted"}, headers=W)
    assert refixes == [job.name]
    client.post(f"/api/lectures/{job.name}/termfix/s1", json={"status": "course"}, headers=W)
    course = {c.id: c for c in settings.cfgmod.load_courses()}["digitale-elektronica"]
    assert course.corrections["nent"] == "NAND" and len(refixes) == 2
    client.post(f"/api/lectures/{job.name}/termfix/s1", json={"status": "open"}, headers=W)  # undo
    course = {c.id: c for c in settings.cfgmod.load_courses()}["digitale-elektronica"]
    assert "nent" not in course.corrections and len(refixes) == 3
    assert client.post(f"/api/lectures/{job.name}/termfix/s9", json={"status": "accepted"}, headers=W).status_code == 404
    assert client.post(f"/api/lectures/{job.name}/termfix/s1", json={"status": "x"}, headers=W).status_code == 409

    started = []
    monkeypatch.setattr(pipeline, "run_termfix", lambda job, conf, rep: started.append(job.root.name))
    assert client.post(f"/api/lectures/{job.name}/termfix/run", headers=W).json() == {"status": "running"}
    # still "running" (the fake never finishes the file): a second click is refused
    assert client.post(f"/api/lectures/{job.name}/termfix/run", headers=W).status_code == 409


def test_inbox_waiting_and_add_page_know_the_course_folder(env, tmp_path):
    from lecture.api import queue as queue_api

    client, queue, video, job = env
    queue_api._inbox_cache.update(at=0.0, data=None)
    shelf = tmp_path / "inbox" / "digitale-elektronica"
    shelf.mkdir(parents=True)
    (shelf / "les 3.pdf").write_bytes(b"%PDF")
    (shelf / "DEP les 7.mp4").write_bytes(b"x" * 10)        # its deck (les 7) isn't there yet
    d = client.get("/api/inbox").json()
    assert [(w["title"], w["course"], w["ready"]) for w in d["waiting"]] == [("Les 7", "digitale-elektronica", False)]
    assert "lecture 7" in d["waiting"][0]["why"] and (tmp_path / "inbox" / "algemene-economie").is_dir()
    s = client.get("/api/suggestions").json()
    assert {(v["name"], v["course"]) for v in s["videos"]} >= {("DEP les 7.mp4", "digitale-elektronica")}
    assert ("les 3.pdf", "digitale-elektronica") in {(x["name"], x["course"]) for x in s["slides"]}


def test_mac_address_and_test_in_settings(env, monkeypatch):
    from lecture import models

    client, *_ = env
    assert client.get("/api/setup").json()["mac"] == {"url": "http://my-mac:7862", "token": False}
    assert client.post("/api/setup/mac", json={"url": "ftp://x"}, headers=W).status_code == 400
    r = client.post("/api/setup/mac", json={"url": " http://mac-mini:7900/ "}, headers=W).json()
    assert r == {"url": "http://mac-mini:7900"} and client.get("/api/setup").json()["mac"]["url"] == r["url"]
    assert client.post("/api/setup/mac/test", headers=W).json() == {"ok": False, "detail": "LECTURE_MAC_TOKEN missing"}
    assert client.post("/api/setup/key", json={"name": "mac", "value": "a" * 43}, headers=W).status_code == 200
    seen = []
    monkeypatch.setattr("lecture.providers.mac_whisper.MacWhisper.health",
                        lambda self: seen.append(self.mc.url) or {"models": ["large-v3"], "llm_models": ["qwen3.8:27b"]})
    t = client.post("/api/setup/mac/test", headers=W).json()
    assert t["ok"] and t["whisper"].startswith("large-v3 ready") and t["llm"] == "qwen3.8:27b ready"
    assert seen == ["http://mac-mini:7900"]


def test_stop_buttons_reach_the_worker_and_the_inbox(env, tmp_path):
    import time as _time
    from lecture import inbox
    from lecture.api import queue as queue_api

    client, queue, video, job = env
    item = queue.add(video, "digitale-elektronica")
    assert client.post(f"/api/queue/{item['id']}/stop", headers=W).status_code == 409   # nothing running yet
    queue.claim_transcription(pid=1)
    assert client.post(f"/api/queue/{item['id']}/stop", headers=W).json() == {"ok": True}
    assert queue.stop_requested(item["id"])

    # A pair being combined in the watch folder: Stop puts it on the inbox's ignore list.
    folder = tmp_path / "inbox" / "digitale-elektronica"
    folder.mkdir(parents=True)
    for name in ("les 9.webcam.mp4", "les 9.mp4"):
        (folder / name).write_bytes(b"x")
    old = _time.time() - 600
    import os
    for f in folder.iterdir():
        os.utime(f, (old, old))
    queue_api._inbox_cache["data"] = None
    assert client.post("/api/inbox/stop", json={"media": str(folder / "nope.mp4")}, headers=W).status_code == 404
    assert client.post("/api/inbox/stop", json={"media": str(folder / "les 9.mp4")}, headers=W).json() == {"ok": True}
    from lecture.config import load_config
    assert str((folder / "les 9.mp4").resolve()) in inbox.ignored(load_config())


def test_share_reads_a_real_job(env):
    from lecture import share
    _, _, video, job = env
    [x] = share._local({"digitale-elektronica"})
    assert x["id"] == job.name and x["_data"]["segments"][0]["text"] == "Hallo"
    assert x["_data"]["summary"]["title"] == "Les 4" and str(video.parent) not in repr(x["_data"])
    assert share._local({"ander-vak"}) == []


def test_share_settings_without_a_hub(env):
    client = env[0]
    assert client.get("/api/share").json()["hub"] is False
    assert client.post("/api/share/codes", headers=W, json={"name": "Jan", "courses": ["nope"]}).status_code == 400


def test_simple_mode_hides_latex(env):
    client, _, _, job = env
    (job / "sections.json").write_text("{}")
    assert client.get("/api/setup").json()["simple"] is False
    assert client.get(f"/api/lectures/{job.name}").json()["can_latex"] is True
    conf = job.parents[1] / "xdg-config"
    path = next(conf.rglob("config.yaml"))
    path.write_text(path.read_text() + "app:\n  simple: true\n")
    assert client.get("/api/setup").json()["simple"] is True
    assert client.get(f"/api/lectures/{job.name}").json()["can_latex"] is False
