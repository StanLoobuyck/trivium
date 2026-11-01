"""Mac model-server provider against a fake server (httpx MockTransport): no network, no Mac."""

from __future__ import annotations

import httpx
import pytest

from lecture import pipeline, status
from lecture.config import load_config
from lecture.providers.mac_whisper import MacUnavailable, MacWhisper
from lecture.report import NullReporter

RESPONSE = {"task": "transcribe", "language": "nl", "duration": 2.0, "text": " NAND-poort",
            "segments": [{"id": 0, "start": 0.0, "end": 2.0, "text": " NAND-poort", "avg_logprob": -0.2,
                          "no_speech_prob": 0.01, "compression_ratio": 1.0, "temperature": 0.0}],
            "words": [{"word": "NAND-poort", "start": 0.1, "end": 1.0}], "x_mac": {"model": "large-v3"}}


def fake_mac(conf, handler) -> MacWhisper:
    client = httpx.Client(base_url=conf.stt.mac.url, transport=httpx.MockTransport(handler),
                          headers={"Authorization": "Bearer t0ken"})
    return MacWhisper(conf, "t0ken", client=client)


def test_health_and_transcribe_send_laptop_settings(xdg, tmp_path):
    conf = load_config()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["authorization"] == "Bearer t0ken"
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "models": ["large-v3", "large-v3-turbo"], "busy": False})
        body = request.content.decode("latin-1")
        # decoding settings come from config.yaml (the laptop is the single source)
        for field, value in (("language", "nl"), ("model", conf.stt.mac.model), ("prompt", "Dit is een les"),
                             ("temperature", ",".join(str(t) for t in conf.stt.local.temperatures)),
                             ("condition_on_previous_text", "false")):
            assert f'name="{field}"\r\n\r\n{value}\r\n' in body, field
        return httpx.Response(200, json=RESPONSE)

    clip = tmp_path / "c.flac"
    clip.write_bytes(b"fLaC fake")
    stt = fake_mac(conf, handler)
    stt.check()
    t = stt.transcribe(clip, 2.0, "nl", "Dit is een les")
    assert t.response == RESPONSE and t.model == f"mac:{conf.stt.mac.model}" and t.attempts == 1
    assert [r.url.path for r in seen] == ["/health", "/v1/audio/transcriptions"]


def test_unreachable_wrong_token_or_model_is_unavailable(xdg):
    conf = load_config()

    def down(request):
        raise httpx.ConnectError("no route to host")

    with pytest.raises(MacUnavailable, match="not reachable"):
        fake_mac(conf, down).check()
    with pytest.raises(MacUnavailable, match="token"):
        fake_mac(conf, lambda r: httpx.Response(401)).check()
    with pytest.raises(MacUnavailable, match="doesn't offer"):
        fake_mac(conf, lambda r: httpx.Response(200, json={"models": ["tiny"]})).check()


def test_transient_server_error_is_retried(xdg, tmp_path, monkeypatch):
    conf = load_config()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json=RESPONSE)

    monkeypatch.setattr("lecture.providers.mac_whisper._sleep", lambda s: None)
    clip = tmp_path / "c.flac"
    clip.write_bytes(b"x")
    t = fake_mac(conf, handler).transcribe(clip, 2.0, "nl", "")
    assert t.attempts == 2


def test_chain_skips_mac_without_token_and_never_probes_local_first(xdg, monkeypatch):
    conf = load_config()
    assert conf.stt.providers[0] == "mac"
    order = []
    monkeypatch.setitem(pipeline._STT_FACTORIES, "local",
                        lambda c, r: order.append("local") or type("L", (), {"name": "local"})())
    warnings = []
    rep = type("R", (NullReporter,), {"warn": lambda self, m: warnings.append(m)})()
    # no LECTURE_MAC_TOKEN (xdg fixture clears keys): skipped at once, no network call
    assert pipeline.get_stt(conf, rep).name == "local"
    assert any("mac" in w and "LECTURE_MAC_TOKEN" in w for w in warnings)
    # Mac available → local is never constructed (the NVIDIA GPU stays asleep)
    order.clear()
    monkeypatch.setitem(pipeline._STT_FACTORIES, "mac", lambda c, r: type("M", (), {"name": "mac"})())
    assert pipeline.get_stt(conf, rep).name == "mac" and order == []


def test_gpu_status_does_not_wake_a_sleeping_gpu(monkeypatch):
    monkeypatch.setattr(status.shutil, "which", lambda b: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(status.subprocess, "run", lambda *a, **k: pytest.fail("nvidia-smi was called"))
    monkeypatch.setattr(status, "nvidia_power_state", lambda: "suspended")
    assert "asleep" in status.gpu()
    monkeypatch.setattr(status, "nvidia_power_state", lambda: None)
    assert "no NVIDIA GPU visible" in status.gpu()


def test_mac_that_stops_answering_becomes_unavailable(xdg, tmp_path, monkeypatch):
    monkeypatch.setattr("lecture.providers.mac_whisper._sleep", lambda s: None)
    conf = load_config()
    clip = tmp_path / "c.flac"
    clip.write_bytes(b"x")
    calls = []

    def gone(request):
        calls.append(request)
        raise httpx.ConnectTimeout("Mac left Tailscale")

    with pytest.raises(MacUnavailable, match="stopped answering"):
        fake_mac(conf, gone).transcribe(clip, 600.0, "nl", "")
    assert len(calls) == conf.transcribe.max_attempts
    # short connect timeout; read timeout scaled to the chunk (600 s → 420 s), never above timeout_s
    t = calls[0].extensions["timeout"]
    assert t["connect"] == conf.stt.mac.health_timeout_s and t["read"] == 420.0
    # the time budget stops retrying too (here: no time at all → one attempt)
    calls.clear()
    conf.stt.mac.give_up_after_s = 0
    with pytest.raises(MacUnavailable):
        fake_mac(conf, gone).transcribe(clip, 600.0, "nl", "")
    assert len(calls) == 1
    # a real error (bad request) is not a dropout: it is raised as is
    with pytest.raises(httpx.HTTPStatusError):
        fake_mac(conf, lambda r: httpx.Response(400)).transcribe(clip, 2.0, "nl", "")


def test_carry_prompt_is_sent_only_when_asked(xdg, tmp_path):
    conf = load_config()
    bodies = []

    def handler(request):
        bodies.append(request.content.decode("latin-1"))
        return httpx.Response(200, json=RESPONSE)

    clip = tmp_path / "c.flac"
    clip.write_bytes(b"x")
    stt = fake_mac(conf, handler)
    stt.transcribe(clip, 2.0, "nl", "Dit is een les over NAND.")
    stt.transcribe(clip, 2.0, "nl", "Dit is een les over NAND. vorige woorden", carry_prompt="Dit is een les over NAND.")
    assert 'name="carry_prompt"' not in bodies[0]
    assert 'name="carry_prompt"\r\n\r\nDit is een les over NAND.\r\n' in bodies[1]
