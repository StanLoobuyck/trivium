"""Model registry (Settings › add models, speech-to-text order, Test) — offline, no network."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lecture import config as cfg
from lecture import models, pipeline, webapp
from lecture.providers.llm import LLMUnavailable
from lecture.providers.openai_llm import OpenAICompatLLM
from lecture.report import NullReporter

W = {"x-lecture-ui": "1"}


def test_add_order_and_remove_models(xdg):
    sid = models.add_model("stt", "mac", "large-v3-turbo", "Turbo op de Mac")
    nid = models.add_model("notes", "ollama-mac", "qwen3:14b")
    conf = cfg.load_config()
    assert conf.stt.providers[-1] == f"custom:{sid}" and conf.model_entry(f"custom:{sid}").model == "large-v3-turbo"
    m = conf.model_entry(f"custom:{nid}")
    assert (m.provider, m.base_url, m.key_name) == ("openai", "http://my-mac:11434/v1", None)
    assert f"custom:{nid}" in conf.llm.notes_choices
    # reorder: the added model first; unknown entries are refused
    models.set_stt_order([f"custom:{sid}", "mac", "local", "groq"])
    assert cfg.load_config().stt.providers[0] == f"custom:{sid}"
    with pytest.raises(ValueError):
        models.set_stt_order(["mac", "custom:nope"])
    # removing a model also takes it out of every chain
    models.remove_model(sid)
    models.remove_model(nid)
    conf = cfg.load_config()
    assert conf.models == [] and conf.stt.providers == ["mac", "local", "groq"]
    assert not any(c.startswith("custom:") for c in conf.llm.notes_choices)


def test_bad_models_are_refused_and_nothing_is_written(xdg):
    with pytest.raises(ValueError):
        models.add_model("notes", "openai", "x")  # an OpenAI-compatible server needs base_url
    with pytest.raises(ValueError):
        models.add_model("stt", "claude", "x")    # not a speech-to-text provider
    assert cfg.load_config().models == []


def test_custom_entries_become_the_right_providers(xdg, monkeypatch):
    sid = models.add_model("stt", "mac", "large-v3-turbo")
    gid = models.add_model("stt", "groq", "whisper-large-v3-turbo")
    nid = models.add_model("notes", "openrouter", "some/model")
    conf = cfg.load_config()
    made = {}
    monkeypatch.setattr(pipeline, "_mac", lambda c, r, model=None: made.setdefault("mac", type("M", (), {"name": "mac", "model": model})()))
    monkeypatch.setattr(pipeline, "_groq", lambda c, r: type("G", (), {"transcribe": lambda *a, **k: k["model"]})())
    stt = pipeline.stt_factory(f"custom:{sid}")(conf, NullReporter())
    assert stt.name == f"custom:{sid}" and made["mac"].model == "large-v3-turbo"
    g = pipeline.stt_factory(f"custom:{gid}")(conf, NullReporter())
    assert g.name == f"custom:{gid}" and g.transcribe("a", 1.0, "nl", "") == "whisper-large-v3-turbo"
    # an OpenRouter model without its key: unavailable (next provider), not a crash
    with pytest.raises(LLMUnavailable, match="OPENROUTER_API_KEY"):
        pipeline.notes_factory(conf, NullReporter(), f"custom:{nid}")()


def test_openai_compatible_notes_provider_parses_json():
    entry = cfg.ModelEntry(id="q", kind="notes", provider="openai", model="qwen3:14b", base_url="http://x/v1")
    sent = {}

    class Completions:
        def create(self, **kw):
            sent.update(kw)
            msg = type("Msg", (), {"content": '```json\n{"ok": true}\n```'})()
            choice = type("C", (), {"message": msg, "finish_reason": "stop"})()
            return type("R", (), {"choices": [choice], "model": "qwen3:14b", "usage": None})()

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})()})()
    llm = OpenAICompatLLM(type("Conf", (), {"notes": type("N", (), {"timeout_s": 5})()})(), entry, client=client)
    out = llm.generate("system", "user", {"type": "object"})
    assert out.data == {"ok": True} and sent["model"] == "qwen3:14b"
    assert sent["response_format"]["type"] == "json_schema"


def test_models_api(xdg):
    client = TestClient(webapp.create_app(), base_url="http://127.0.0.1")
    r = client.post("/api/models", json={"kind": "stt", "preset": "mac", "model": "large-v3-turbo"}, headers=W)
    assert r.status_code == 200
    sid = r.json()["id"]
    assert client.get("/api/models").json()["models"][0]["id"] == sid
    assert client.post("/api/models", json={"kind": "notes", "preset": "openai", "model": "x"}, headers=W).status_code == 400
    assert client.post("/api/models/order", json={"order": ["groq", f"custom:{sid}"]}, headers=W).status_code == 200
    assert cfg.load_config().stt.providers == ["groq", f"custom:{sid}"]
    assert client.post("/api/models/order", json={"order": ["groq"]}).status_code == 403  # writes need the UI header
    assert client.delete(f"/api/models/{sid}", headers=W).status_code == 200
    assert cfg.load_config().stt.providers == ["groq"]
