"""Local Whisper picks its device: the GPU when it works, else the processor (stt.local.device: auto)."""

import sys
import types

import pytest

from lecture.config import load_config
from lecture.providers import local_whisper as lw


@pytest.fixture
def fake_whisper(monkeypatch):
    loads = []

    class WhisperModel:
        def __init__(self, model, device, compute_type):
            loads.append((model, device, compute_type))
            if device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModel))
    monkeypatch.setattr(lw, "preload_cuda_libraries", lambda: [])
    return loads


def conf_with(device, xdg):
    xdg.mkdir(parents=True, exist_ok=True)
    (xdg / "config.yaml").write_text(f"stt:\n  local:\n    device: {device}\n    model: small\n")
    return load_config()


def test_auto_falls_back_to_the_processor(xdg, fake_whisper, monkeypatch):
    monkeypatch.setattr(lw, "resolve_device", lambda device: "cuda")
    w = lw.LocalWhisper(conf_with("auto", xdg))
    w.check()
    assert w.device == "cpu" and w._compute_type == "int8"
    assert fake_whisper[-1] == ("small", "cpu", "int8") and fake_whisper[0][1] == "cuda"


def test_cuda_only_does_not_fall_back(xdg, fake_whisper, monkeypatch):
    w = lw.LocalWhisper(conf_with("cuda", xdg))
    with pytest.raises(lw.LocalUnavailable):
        w.check()
    assert {d for _, d, _ in fake_whisper} == {"cuda"}


def test_cpu_uses_cpu_compute_types(xdg, fake_whisper):
    w = lw.LocalWhisper(conf_with("cpu", xdg))
    w.check()
    assert fake_whisper == [("small", "cpu", "int8")]


def test_resolve_device_without_cuda(monkeypatch):
    monkeypatch.setattr(lw, "preload_cuda_libraries", lambda: [])
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: 0))
    assert lw.resolve_device("auto") == "cpu"
    assert lw.resolve_device("cuda") == "cuda"
