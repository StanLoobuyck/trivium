"""Verbatim delen: beheer met de koppelcode, bekijken met een deelcode die niets van Sequo opent."""
import pytest
from fastapi.testclient import TestClient

from hub.app import create_app

CODE = "x" * 40
AUTH = {"Authorization": f"Bearer {CODE}"}
LES = {"course": "vak-a", "hash": "h1", "data": {
    "summary": {"id": "les-1", "title": "Les 1", "course": "vak-a", "course_name": "Vak A"},
    "segments": [{"start": 3725.0, "end": 3727.0, "text": "Hallo"}]}}


@pytest.fixture
def hub(tmp_path):
    web = tmp_path / "share-web"
    web.mkdir()
    (web / "share.html").write_text("<h1>Gedeeld</h1>")
    return TestClient(create_app(code=CODE, db_path=tmp_path / "hub.sqlite", share_web=str(web)))


def make_code(hub, courses=("vak-a",)):
    r = hub.post("/api/share/codes", headers=AUTH, json={"name": "Jan", "courses": [{"id": c, "name": c} for c in courses]})
    assert r.status_code == 200
    return r.json()


def upload(hub, lecture_id="les-1", body=LES, video=b"0123456789" * 100):
    assert hub.put(f"/api/share/lectures/{lecture_id}", headers=AUTH, json=body).status_code == 200
    assert hub.put(f"/api/share/lectures/{lecture_id}/video", headers=AUTH, content=video).json() == {"size": len(video)}
    assert hub.put(f"/api/share/lectures/{lecture_id}/subtitles?hash=s1", headers=AUTH, content=b"WEBVTT\n").status_code == 200


def login(hub, code):
    r = hub.post("/share/api/login", json={"code": code})
    assert r.status_code == 200 and r.json() == {"name": "Jan"}


def test_beheer_vraagt_de_koppelcode(hub):
    assert hub.get("/api/share").status_code == 401
    assert hub.post("/api/share/codes", json={"name": "Jan", "courses": []}).status_code == 401
    assert hub.put("/api/share/lectures/les-1", json=LES).status_code == 401
    code = make_code(hub)
    assert len(code["code"]) >= 24
    assert hub.get("/api/share", headers=AUTH).json()["codes"][0]["name"] == "Jan"


def test_deelcode_ziet_alleen_haar_vakken(hub):
    code = make_code(hub)
    upload(hub)
    upload(hub, "les-2", {**LES, "course": "vak-b", "data": {"summary": {"id": "les-2", "course": "vak-b"}}})
    login(hub, code["code"])
    assert [x["id"] for x in hub.get("/share/api/lectures").json()] == ["les-1"]
    les = hub.get("/share/api/lectures/les-1").json()
    assert les["has_video"] and les["has_subtitles"] and les["segments"][0]["text"] == "Hallo"
    assert hub.get("/share/api/lectures/les-2").status_code == 404
    assert hub.get("/share/api/lectures/les-2/video").status_code == 404


def test_video_met_range_en_download(hub):
    login(hub, make_code(hub)["code"])
    upload(hub)
    part = hub.get("/share/api/lectures/les-1/video", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == b"0123456789"
    assert "inline" in part.headers.get("content-disposition", "inline")
    down = hub.get("/share/api/lectures/les-1/video?download=1")
    assert down.headers["content-disposition"].startswith("attachment") and "Vak%20A%20-%20Les%201.mp4" in down.headers["content-disposition"]
    assert hub.get("/share/api/lectures/les-1/subtitles.vtt").headers["content-type"].startswith("text/vtt")
    txt = hub.get("/share/api/lectures/les-1/transcript.txt")
    assert txt.text == "[1:02:05] Hallo\n" and txt.headers["content-disposition"].startswith("attachment")


def test_deelcode_opent_niets_van_sequo(hub):
    code = make_code(hub)["code"]
    login(hub, code)
    share_auth = {"Authorization": f"Bearer {code}"}
    for path in ("/api/courses", "/api/events", "/api/rooster", "/api/share"):
        assert hub.get(path, headers=share_auth).status_code == 401
    assert hub.post("/api/sync", headers=share_auth, json={"cursor": 0, "changes": []}).status_code == 401


def test_koppelcode_is_geen_deelcode(hub):
    assert hub.post("/share/api/login", json={"code": CODE}).status_code == 401
    hub.cookies.set("verbatim_share", CODE, path="/share")
    assert hub.get("/share/api/lectures").status_code == 401
    assert hub.get("/share/api/me").status_code == 401


def test_intrekken_en_vakken_wijzigen(hub):
    code = make_code(hub)
    upload(hub)
    login(hub, code["code"])
    hub.patch(f"/api/share/codes/{code['id']}", headers=AUTH, json={"courses": []})
    assert hub.get("/share/api/lectures").json() == []
    hub.delete(f"/api/share/codes/{code['id']}", headers=AUTH)
    assert hub.get("/share/api/me").status_code == 401


def test_les_verwijderen_wist_de_bestanden(hub, tmp_path):
    upload(hub)
    assert (tmp_path / "share" / "les-1" / "video.mp4").is_file()
    hub.delete("/api/share/lectures/les-1", headers=AUTH)
    assert not (tmp_path / "share" / "les-1").exists()
    assert hub.get("/api/share", headers=AUTH).json()["lectures"] == []


def test_vreemde_namen_worden_geweigerd(hub):
    for bad in ("..", ".verborgen", "a%2Fb"):
        assert hub.put(f"/api/share/lectures/{bad}", headers=AUTH, json=LES).status_code in (404, 405)


def test_pagina_en_sequo_naast_elkaar(hub):
    assert hub.get("/share/").text == "<h1>Gedeeld</h1>"
    assert hub.get("/share/static/share.html").status_code == 200


def test_kleur_per_vak_gaat_mee(hub):
    r = hub.post("/api/share/codes", headers=AUTH, json={"name": "Jan", "courses": [{"id": "vak-a", "name": "A", "color": "purple"}]})
    login(hub, r.json()["code"])
    me = hub.get("/share/api/me").json()
    assert me["courses"] == [{"id": "vak-a", "name": "A", "color": "purple"}] and me["code"] == r.json()["code"]
    bad = hub.post("/api/share/codes", headers=AUTH, json={"name": "Jan", "courses": [{"id": "vak-a", "name": "A", "color": "<b>"}]})
    assert bad.status_code == 422
