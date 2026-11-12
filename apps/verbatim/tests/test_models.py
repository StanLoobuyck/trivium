"""Model registry (Settings › add models, speech-to-text order, Test) — offline, no network."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lecture import config as cfg
from lecture import models, pipeline, settings, webapp
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
        models.add_model("notes", "other", "x")  # another OpenAI-compatible server needs base_url
    with pytest.raises(ValueError, match="paste the API key"):
        models.add_model("notes", "openai", "gpt-x")  # OpenAI needs a key the first time
    with pytest.raises(ValueError):
        models.add_model("stt", "claude", "x")    # not a speech-to-text provider
    assert cfg.load_config().models == []


def test_custom_entries_become_the_right_providers(xdg, monkeypatch):
    sid = models.add_model("stt", "mac", "large-v3-turbo")
    gid = models.add_model("stt", "groq", "whisper-large-v3-turbo")
    nid = models.add_model("notes", "openrouter", "some/model", key="sk-or-" + "k" * 30)
    settings.remove_key("openrouter")  # removed later under Connections
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


def test_own_keys_in_the_add_form(xdg):
    """Owner's choice 2026-11-12: the key goes in the Add-model form, is saved per provider and reused."""
    oid = models.add_model("notes", "openai", "gpt-x", key="sk-proj-" + "a" * 30)
    assert cfg.load_keys()["OPENAI_API_KEY"] == "sk-proj-" + "a" * 30
    models.add_model("notes", "openai", "gpt-y")  # key already saved: no need to paste it again
    aid = models.add_model("notes", "anthropic", "claude-x", key="sk-ant-" + "b" * 30)
    other = models.add_model("notes", "other", "local-x", "LM Studio", base_url="http://localhost:1234/v1",
                             key="lm-" + "c" * 20)
    conf = cfg.load_config()
    a = conf.model_entry(f"custom:{aid}")
    assert (a.provider, a.base_url, a.key_name) == ("openai", "https://api.anthropic.com/v1/", "ANTHROPIC_API_KEY")
    o = conf.model_entry(f"custom:{other}")
    assert o.key_name == "LM_STUDIO_API_KEY" and cfg.load_keys()["LM_STUDIO_API_KEY"] == "lm-" + "c" * 20
    assert f"custom:{oid}" in conf.llm.notes_choices
    # Connections lists every key in use, never the key itself
    listed = {k["name"]: k for k in settings.api_keys(conf)}
    assert listed["openai"]["set"] and listed["anthropic"]["set"] and listed["LM_STUDIO_API_KEY"]["set"]
    assert "a" * 30 not in str(listed)
    settings.remove_key("LM_STUDIO_API_KEY")
    assert not cfg.load_keys().get("LM_STUDIO_API_KEY")
    with pytest.raises(ValueError):
        settings.set_key("PATH", "x" * 20)  # only API keys, nothing else in .env


def test_notes_models_start_empty_and_all_can_be_removed(xdg, tmp_path):
    settings.setup_simple(tmp_path / "Lessen")
    conf = cfg.load_config()
    assert conf.llm.notes_choices == [] and conf.llm.tasks["notes"] == []
    # no model: the job waits with a reason instead of crashing
    ((label, make),) = pipeline.notes_providers(conf, NullReporter())
    with pytest.raises(LLMUnavailable, match="no notes model"):
        make()
    # a Gemini key adds Gemini once, and it writes the notes
    settings.set_key("gemini", "AIza" + "g" * 30)
    settings.set_key("gemini", "AIza" + "h" * 30)
    conf = cfg.load_config()
    assert conf.llm.notes_choices == [settings.GEMINI_NOTES] and conf.llm.tasks["notes"] == [settings.GEMINI_NOTES]
    # an update (setup-simple again) keeps the user's list
    nid = models.add_model("notes", "mistral", "mistral-x", key="ms-" + "m" * 30)
    settings.setup_simple(tmp_path / "Lessen")
    assert cfg.load_config().llm.notes_choices == [settings.GEMINI_NOTES, f"custom:{nid}"]
    # built-in models can be removed too; the next one takes over
    models.remove_notes_choice(settings.GEMINI_NOTES)
    conf = cfg.load_config()
    assert conf.llm.notes_choices == [f"custom:{nid}"] and conf.llm.tasks["notes"][0] == f"custom:{nid}"
    models.remove_notes_choice(f"custom:{nid}")
    conf = cfg.load_config()
    assert conf.llm.notes_choices == [] and conf.llm.tasks["notes"] == [] and conf.models == []


def test_remove_builtin_notes_model_api(xdg):
    client = TestClient(webapp.create_app(), base_url="http://127.0.0.1")
    first = cfg.load_config().llm.notes_choices[0]
    assert client.post("/api/models/notes/remove", json={"entry": first}, headers=W).status_code == 200
    assert first not in cfg.load_config().llm.notes_choices
    assert client.post("/api/models/notes/remove", json={"entry": "gemini:nope"}, headers=W).status_code == 400
    s = client.get("/api/setup").json()
    assert "api_keys" in s and all("value" not in k for k in s["api_keys"])


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
