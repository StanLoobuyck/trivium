"""Sharing through the hub: what goes up, what comes off, and that private fields stay home."""

import pytest

from lecture import share


def item(id, course="vak-a", hash="h", video=None, subs=None):
    return {"id": id, "course": course, "hash": hash, "video_size": video.stat().st_size if video else 0,
            "subtitles_hash": "s" if subs else "", "_data": {"summary": {"id": id}}, "_video": video, "_subs": subs}


def test_plan():
    local = [{"id": "a", "course": "x", "hash": "1", "video_size": 5, "subtitles_hash": ""},
             {"id": "b", "course": "x", "hash": "2", "video_size": 5, "subtitles_hash": ""},
             {"id": "c", "course": "y", "hash": "3", "video_size": 5, "subtitles_hash": ""}]
    remote = [{"id": "a", "course": "x", "hash": "1", "video_size": 5, "subtitles_hash": ""},
              {"id": "b", "course": "x", "hash": "old", "video_size": 5, "subtitles_hash": ""},
              {"id": "gone", "course": "x", "hash": "9", "video_size": 1, "subtitles_hash": ""}]
    send, remove = share.plan(local, remote, {"x"})
    assert [x["id"] for x in send] == ["b"]  # a unchanged, c not shared
    assert remove == ["gone"]
    assert share.plan(local, remote, set()) == ([], ["a", "b", "gone"])  # no codes left: everything off


def test_lecture_data_keeps_private_fields_home():
    summary = {"id": "x", "title": "Les 1", "course": "vak", "queue": {"media": "/home/me/x.mp4"}, "models": {"stt": "m"}}
    detail = {"segments": [{"start": 0, "end": 1, "text": "a"}], "sections_detail": [], "notes": None,
              "corrections": {"nent": "NAND"}, "whisper_prompt": "p", "media_name": "x.mp4", "language": "nl"}
    data = share.lecture_data(summary, detail)
    flat = repr(data)
    assert "/home/" not in flat and "corrections" not in flat and "models" not in flat and "x.mp4" not in flat
    assert data["summary"]["title"] == "Les 1" and data["segments"][0]["text"] == "a"


class FakeHub:
    def __init__(self, courses):
        self.codes = [{"id": "c1", "name": "Jan", "courses": [{"id": c, "name": c} for c in courses]}]
        self.lectures, self.calls = {}, []

    def overview(self):
        return {"codes": self.codes, "lectures": list(self.lectures.values())}

    def call(self, method, path, json=None, content=None, params=None):
        self.calls.append((method, path))
        lid = path.split("/")[4]
        if method == "DELETE":
            self.lectures.pop(lid)
        elif path.endswith("/video"):
            self.lectures[lid]["video_size"] = len(content.read())
        elif path.endswith("/subtitles"):
            self.lectures[lid]["subtitles_hash"] = params["hash"]
        else:
            self.lectures[lid] = {"id": lid, "course": json["course"], "hash": json["hash"], "video_size": 0,
                                  "subtitles_hash": ""}
        return {}


@pytest.fixture
def setup(tmp_path, monkeypatch, xdg):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {tmp_path / 'jobs'}\n")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    subs = tmp_path / "s.vtt"
    subs.write_text("WEBVTT\n")
    hub = FakeHub(["vak-a"])
    local = [item("a", video=video, subs=subs), item("b", video=video), item("c", course="vak-b", video=video)]
    monkeypatch.setattr(share, "codes", hub.overview)
    monkeypatch.setattr(share, "hub_call", hub.call)
    monkeypatch.setattr(share, "_local", lambda courses: [x for x in local if x["course"] in courses])
    return hub, local


def test_sync_sends_once_and_one_video_per_round(setup):
    hub, _ = setup
    first = share.sync(max_videos=1, log=lambda m: None)
    assert first["videos"] == 1 and first["videos_waiting"] == 1
    assert set(hub.lectures) == {"a", "b"}  # vak-b is not on any code
    share.sync(max_videos=1, log=lambda m: None)
    assert all(x["video_size"] == 1000 for x in hub.lectures.values())
    hub.calls.clear()
    again = share.sync(log=lambda m: None)
    assert hub.calls == [] and again["sent"] == 0  # nothing changed: nothing sent


def test_unsharing_a_course_takes_its_lectures_off(setup):
    hub, _ = setup
    share.sync(log=lambda m: None)
    hub.codes[0]["courses"] = []
    share.sync(log=lambda m: None)
    assert hub.lectures == {}


def test_a_word_fix_resends_only_the_text(setup):
    hub, local = setup
    share.sync(log=lambda m: None)
    hub.calls.clear()
    local[0]["hash"] = "new"
    share.sync(log=lambda m: None)
    assert hub.calls == [("PUT", "/api/share/lectures/a")]


def test_worker_does_nothing_without_a_hub(monkeypatch):
    monkeypatch.setattr(share, "_link", lambda: None)
    monkeypatch.setattr(share, "sync", lambda **kw: pytest.fail("no hub: no sync"))
    share.sync_quietly()


def test_worker_checks_every_five_minutes_unless_videos_wait(monkeypatch):
    runs = []
    monkeypatch.setattr(share, "_link", lambda: ("http://hub", {}))
    monkeypatch.setattr(share, "_last", {"at": 0.0})
    monkeypatch.setattr(share, "sync", lambda **kw: runs.append(1) or {"videos_waiting": 0})
    share.sync_quietly(now=1000)
    share.sync_quietly(now=1100)
    assert len(runs) == 1
    share.sync_quietly(now=1301)
    assert len(runs) == 2
    monkeypatch.setattr(share, "sync", lambda **kw: runs.append(1) or {"videos_waiting": 3})
    share.sync_quietly(now=2000)
    share.sync_quietly(now=2030)
    assert len(runs) == 4


def test_all_texts_go_up_before_any_video(setup):
    hub, _ = setup
    share.sync(log=lambda m: None)
    kinds = ["video" if p.endswith("/video") else "text" for _, p in hub.calls if not p.endswith("/subtitles")]
    assert kinds == ["text", "text", "video", "video"]  # the page lists both lectures right away
