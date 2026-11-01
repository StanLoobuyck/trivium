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
    (tmp_path / "web" / "index.html").write_text("<h1>Inhaal</h1>")
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
    assert client.get("/api/health").json() == {"app": "inhaal-hub"}
    assert "Inhaal" in client.get("/").text


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
