import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from hub.app import create_app
from hub.rooster import fetch_once, save_rooster
from hub.store import Store

CODE = "x" * 40
AUTH = {"Authorization": f"Bearer {CODE}"}
ICS = "BEGIN:VCALENDAR\nDTSTAMP:1\nBEGIN:VEVENT\nUID:a\nEND:VEVENT\nEND:VCALENDAR\n"


def change(record_id="a", updated="2026-11-01T10:00:00.000Z", status="watched", table="sessions"):
    return {"table": table, "record": {"id": record_id, "updatedAt": updated, "status": status}}


@pytest.fixture
def client(tmp_path):
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "index.html").write_text("<h1>Sequo</h1>")
    return TestClient(create_app(code=CODE, db_path=tmp_path / "hub.sqlite", web_dir=str(tmp_path / "web")))


def sync(client, cursor=0, changes=()):
    response = client.post("/api/sync", headers=AUTH, json={"cursor": cursor, "changes": list(changes)})
    assert response.status_code == 200
    return response.json()


def test_weigert_zonder_of_met_foute_code(client):
    assert client.post("/api/sync", json={}).status_code == 401
    assert client.post("/api/sync", json={}, headers={"Authorization": "Bearer fout"}).status_code == 401
    assert client.get("/api/rooster").status_code == 401


def test_health_en_app_zijn_open(client):
    assert client.get("/api/health").json() == {"app": "trivium-hub"}
    assert "Sequo" in client.get("/").text


def test_een_korte_code_start_niet(tmp_path):
    with pytest.raises(ValueError):
        create_app(code="kort", db_path=tmp_path / "a.sqlite")


def test_tweede_toestel_krijgt_de_wijziging(client):
    first = sync(client, changes=[change()])
    assert first["records"][0]["record"]["status"] == "watched"
    second = sync(client)
    assert [r["record"]["id"] for r in second["records"]] == ["a"]
    assert sync(client, cursor=second["cursor"])["records"] == []


def test_recentste_wint(client):
    sync(client, changes=[change(updated="2026-11-01T12:00:00.000Z", status="watched")])
    sync(client, changes=[change(updated="2026-11-01T11:00:00.000Z", status="skipped")])
    assert sync(client)["records"][0]["record"]["status"] == "watched"
    sync(client, changes=[change(updated="2026-11-01T13:00:00.000Z", status="processed")])
    assert sync(client)["records"][0]["record"]["status"] == "processed"


def test_oude_wijziging_stuurt_niets_opnieuw(client):
    cursor = sync(client, changes=[change()])["cursor"]
    assert sync(client, cursor=cursor, changes=[change()])["records"] == []


def test_verwijderen_komt_door(client):
    cursor = sync(client, changes=[change()])["cursor"]
    deleted = change(updated="2026-11-01T11:00:00.000Z")
    deleted["record"]["deletedAt"] = "2026-11-01T11:00:00.000Z"
    sync(client, changes=[deleted])
    assert sync(client, cursor=cursor)["records"][0]["record"]["deletedAt"]


@pytest.mark.parametrize("bad", [change(table="geheim"), {"table": "sessions", "record": {"id": "a"}}])
def test_weigert_ongeldige_wijzigingen(client, bad):
    response = client.post("/api/sync", headers=AUTH, json={"cursor": 0, "changes": [bad]})
    assert response.status_code == 422


def test_bewaart_alles_na_herstart(tmp_path):
    path = tmp_path / "hub.sqlite"
    sync(TestClient(create_app(code=CODE, db_path=path)), changes=[change()])
    assert len(sync(TestClient(create_app(code=CODE, db_path=path)))["records"]) == 1


def test_rooster_negeert_foutpagina_en_tijdstempel(tmp_path):
    store = Store(tmp_path / "hub.sqlite")
    assert save_rooster(store, ICS)
    digest = store.get_meta("rooster_hash")
    assert not save_rooster(store, "<html>fout</html>")
    assert store.get_meta("rooster_text") == ICS
    assert save_rooster(store, ICS.replace("DTSTAMP:1", "DTSTAMP:2"))
    assert store.get_meta("rooster_hash") == digest
    assert save_rooster(store, ICS.replace("UID:a", "UID:b"))
    assert store.get_meta("rooster_hash") != digest


def test_rooster_ophalen_overleeft_een_netwerkfout(tmp_path, monkeypatch):
    def fail(request):
        raise httpx.ConnectError("weg")

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(fail), **kw))
    store = Store(tmp_path / "hub.sqlite")
    assert asyncio.run(fetch_once(store, "https://example.test/r.ics")) is False


def test_rooster_is_op_te_halen(client):
    save_rooster(client.app.state.store, ICS)
    assert sync(client)["rooster"]
    assert client.get("/api/rooster", headers=AUTH).json()["text"] == ICS


def notes_event(event_id="e1", kind="notes"):
    return {
        "id": event_id, "type": "notes.ready", "source": "verbatim", "occurredAt": "2026-11-01T12:00:00+01:00",
        "payload": {"recording": {"courseCode": "H06F2A"}, "kind": kind, "verbatimJob": "job-1"},
    }


def test_events_are_kept_once_and_need_the_code(client):
    assert client.post("/api/events", json=notes_event()).status_code == 401
    assert client.post("/api/events", json=notes_event(), headers=AUTH).status_code == 200
    assert client.post("/api/events", json=notes_event(), headers=AUTH).status_code == 200
    client.post("/api/events", json=notes_event("e2"), headers=AUTH)
    first = client.get("/api/events", headers=AUTH).json()
    assert [e["id"] for e in first["events"]] == ["e1", "e2"]
    assert first["events"][0]["payload"]["kind"] == "notes"
    assert client.get(f"/api/events?after={first['cursor']}", headers=AUTH).json()["events"] == []


def test_events_refuse_other_types(client):
    event = {**notes_event(), "type": "recording.watched"}
    assert client.post("/api/events", json=event, headers=AUTH).status_code == 422


def test_courses_of_the_active_semester_only(client):
    time = "2026-11-01T10:00:00.000Z"
    rows = [
        ("semesters", {"id": "s1", "updatedAt": time, "isActive": True}),
        ("semesters", {"id": "s0", "updatedAt": time, "isActive": False}),
        ("courses", {"id": "c1", "updatedAt": time, "semesterId": "s1", "name": "SP", "codes": ["H06F2a"], "language": "en", "colorKey": "indigo"}),
        ("courses", {"id": "c2", "updatedAt": time, "semesterId": "s0", "name": "Oud", "codes": ["H00"]}),
        ("courses", {"id": "c3", "updatedAt": time, "semesterId": "s1", "name": "Weg", "codes": ["H01"], "hidden": True}),
        ("courses", {"id": "c4", "updatedAt": time, "semesterId": "s1", "name": "Wis", "codes": ["H02"], "deletedAt": time}),
    ]
    client.post("/api/sync", json={"changes": [{"table": t, "record": r} for t, r in rows]}, headers=AUTH)
    assert client.get("/api/courses").status_code == 401
    assert client.get("/api/courses", headers=AUTH).json()["courses"] == [{"name": "SP", "codes": ["H06F2a"], "language": "en", "colorKey": "indigo", "lectures": []}]


def test_two_active_semesters_newest_upload_wins(client):
    # Twee toestellen uploadden elk een rooster voor ze gesynct waren: beide semesters staan actief.
    time = "2026-11-02T17:00:00.000Z"
    rows = [
        ("semesters", {"id": "a", "createdAt": "2026-11-02T16:44:40.654Z", "updatedAt": time, "isActive": True}),
        ("semesters", {"id": "b", "createdAt": "2026-11-02T16:47:39.430Z", "updatedAt": time, "isActive": True}),
        ("courses", {"id": "c1", "updatedAt": time, "semesterId": "a", "name": "EEA", "codes": ["H01L8a"]}),
        ("courses", {"id": "c2", "updatedAt": time, "semesterId": "b", "name": "EEA", "codes": ["H01L8a"]}),
    ]
    client.post("/api/sync", json={"changes": [{"table": t, "record": r} for t, r in rows]}, headers=AUTH)
    courses = client.get("/api/courses", headers=AUTH).json()["courses"]
    assert [c["name"] for c in courses] == ["EEA"]


def test_courses_carry_lecture_numbers_like_sequo(client):
    # Zelfde telling als computeNumbers: per vak en type, chronologisch; geschrapt en verwijderd tellen niet.
    time = "2026-11-01T10:00:00.000Z"
    def session(i, start, kind="lecture", **extra):
        return ("sessions", {"id": f"x{i}", "updatedAt": time, "courseId": "c1", "type": kind, "start": start, "status": "upcoming", **extra})
    rows = [
        ("semesters", {"id": "s1", "updatedAt": time, "isActive": True}),
        ("courses", {"id": "c1", "updatedAt": time, "semesterId": "s1", "name": "Vak", "codes": ["H00X1a"]}),
        session(3, "2026-10-02T10:00:00.000Z"),
        session(1, "2026-09-22T06:35:00.000Z"),
        session(2, "2026-09-29T06:35:00.000Z", status="cancelled"),
        session(4, "2026-10-05T06:35:00.000Z", kind="exercise"),
        session(5, "2026-10-06T06:35:00.000Z", deletedAt=time),
        session(6, "2026-10-12T22:30:00.000Z"),  # 00:30 in Brussel: telt als 13/10
    ]
    client.post("/api/sync", json={"changes": [{"table": t, "record": r} for t, r in rows]}, headers=AUTH)
    [course] = client.get("/api/courses", headers=AUTH).json()["courses"]
    assert course["lectures"] == [{"date": "2026-09-22", "number": 1}, {"date": "2026-10-02", "number": 2},
                                  {"date": "2026-10-13", "number": 3}]
