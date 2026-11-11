"""Model registry: the models the user adds in Settings (config `models:`), the speech-to-text order, and the
Test button. Chains refer to an added model as "custom:<id>" (stt.providers, llm.tasks.notes); built-in
entries stay as they were ("mac", "local", "groq", "claude:<model>", "gemini:<model>").
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from . import config as cfgmod
from .config import Config, ModelEntry

# Presets for the "Add a model" form: provider type + address + key, so the user only types the model id
NOTES_PRESETS = {
    "ollama-mac": {"provider": "openai", "base_url": "http://my-mac:11434/v1", "key_name": None},
    "groq": {"provider": "openai", "base_url": "https://api.groq.com/openai/v1", "key_name": "GROQ_API_KEY"},
    "openrouter": {"provider": "openai", "base_url": "https://openrouter.ai/api/v1", "key_name": "OPENROUTER_API_KEY"},
    "claude": {"provider": "claude"},
    "gemini": {"provider": "gemini"},
    "openai": {"provider": "openai"},  # any other OpenAI-compatible server: the user gives base_url (+ key name)
}
STT_PRESETS = {"mac": {"provider": "mac"}, "groq": {"provider": "groq"}}


def _settings_models() -> list[dict]:
    from .settings import _read

    return list(_read(cfgmod.settings_path()).get("models") or [])


def new_id(label: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:32] or "model"
    out, n = base, 2
    while out in taken:
        out, n = f"{base}-{n}", n + 1
    return out


def add_model(kind: str, preset: str, model: str, label: str = "", base_url: str | None = None,
              key_name: str | None = None) -> str:
    """Add a model (validated by loading the config); speech-to-text models go to the end of the order."""
    from .settings import update_settings

    presets = STT_PRESETS if kind == "stt" else NOTES_PRESETS
    if preset not in presets:
        raise ValueError(f"unknown provider {preset!r}")
    conf = cfgmod.load_config()
    spec = {**presets[preset]}
    if preset == "ollama-mac":  # same machine as the speech-to-text server
        spec["base_url"] = f"http://{urlsplit(conf.stt.mac.url).hostname}:11434/v1"
    if spec["provider"] == "openai" and preset == "openai":
        spec.update(base_url=base_url, key_name=key_name or None)
    entry = {"id": new_id(label or model, {m.id for m in conf.models}), "kind": kind, "model": model.strip(),
             "label": label.strip(), **{k: v for k, v in spec.items() if v is not None}}
    ModelEntry.model_validate(entry)
    patch: dict[str, Any] = {"models": [*_settings_models(), entry]}
    if kind == "stt":
        patch["stt"] = {"providers": [*conf.stt.providers, f"custom:{entry['id']}"]}
    else:
        patch["llm"] = {"notes_choices": [*conf.llm.notes_choices, f"custom:{entry['id']}"]}
    update_settings(patch)
    return entry["id"]


def remove_model(model_id: str) -> None:
    from .settings import update_settings

    conf = cfgmod.load_config()
    ref = f"custom:{model_id}"
    rest = [m for m in _settings_models() if m.get("id") != model_id]
    patch: dict[str, Any] = {"models": rest}
    if ref in conf.stt.providers:
        order = [p for p in conf.stt.providers if p != ref]
        patch["stt"] = {"providers": order or ["groq"]}
    if ref in conf.llm.notes_choices or ref in conf.llm.tasks["notes"]:
        patch["llm"] = {"notes_choices": [c for c in conf.llm.notes_choices if c != ref],
                        "tasks": {"notes": [c for c in conf.llm.tasks["notes"] if c != ref] or conf.llm.tasks["notes"][:1]}}
    update_settings(patch)


def set_stt_order(order: list[str]) -> None:
    from .settings import update_settings

    conf = cfgmod.load_config()
    known = {"mac", "local", "groq"} | {f"custom:{m.id}" for m in conf.models if m.kind == "stt"}
    if not order or set(order) - known:
        raise ValueError(f"unknown speech-to-text entries: {', '.join(sorted(set(order) - known)) or '(empty)'}")
    update_settings({"stt": {"providers": order}})


def label(conf: Config, entry: str) -> str:
    if entry.startswith("custom:"):
        m = conf.model_entry(entry)
        return m.label or m.model
    return entry


# --- Test button -----------------------------------------------------------------------------------------

def _tone(path: Path) -> Path:
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                    "-ac", "1", "-ar", "16000", str(path)], check=True)
    return path


def test_stt(conf: Config, entry: str) -> dict[str, Any]:
    """One 2 s request through this speech-to-text entry: does it work, and how long the round trip takes."""
    from .pipeline import stt_factory
    from .report import NullReporter

    t0 = time.monotonic()
    try:
        stt = stt_factory(entry)(conf, NullReporter())
        with tempfile.TemporaryDirectory() as tmp:
            stt.transcribe(_tone(Path(tmp) / "tone.flac"), 2.0, "nl", "")
        if hasattr(stt, "close"):
            stt.close()
    except Exception as exc:  # noqa: BLE001 — the reason is what the user needs to see
        return {"ok": False, "seconds": round(time.monotonic() - t0, 1), "detail": str(exc)[:300]}
    return {"ok": True, "seconds": round(time.monotonic() - t0, 1), "detail": ""}


def test_notes(conf: Config, entry: str) -> dict[str, Any]:
    """A tiny structured request through this notes entry."""
    from .pipeline import notes_factory
    from .report import NullReporter

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    t0 = time.monotonic()
    try:
        llm = notes_factory(conf, NullReporter(), entry)()
        result = llm.generate("You check that a connection works.", 'Reply with {"ok": true}.', schema)
        if not isinstance(result.data, dict):
            raise ValueError("answer is not a JSON object")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "seconds": round(time.monotonic() - t0, 1), "detail": str(exc)[:300]}
    return {"ok": True, "seconds": round(time.monotonic() - t0, 1), "detail": result.model}


# --- availability (shared by /api/setup and /api/models; cheap: no paid calls) ------------------------------

_mac_cache: dict[str, Any] = {"at": -1e9, "info": None, "error": "not checked"}


def mac_health(conf: Config, max_age_s: float = 30.0) -> tuple[dict | None, str]:
    """(health info or None, error) of the Mac's model server; cached because the dashboard asks every 3 s."""
    if conf.stt.mac is None:
        return None, "not configured"
    if time.monotonic() - _mac_cache["at"] < max_age_s:
        return _mac_cache["info"], _mac_cache["error"]
    from .providers.mac_whisper import MacUnavailable, MacWhisper

    token = cfgmod.load_keys()["LECTURE_MAC_TOKEN"]
    if not token:
        return None, "LECTURE_MAC_TOKEN missing"
    stt = MacWhisper(conf, token)
    try:
        info, error = stt.health(), ""
    except MacUnavailable as exc:
        info, error = None, str(exc)
    finally:
        stt.close()
    _mac_cache.update(at=time.monotonic(), info=info, error=error)
    return info, error


def stt_status(conf: Config, entry: str, gpu_ok: bool, groq_key: bool) -> tuple[bool, str]:
    """(usable, detail) of one speech-to-text chain entry."""
    provider, model = entry, None
    if entry.startswith("custom:"):
        m = conf.model_entry(entry)
        provider, model = m.provider, m.model
    if provider == "mac":
        info, error = mac_health(conf)
        if info is None:
            return False, error
        model = model or conf.stt.mac.model
        if model not in info.get("models", []):
            return False, f"the Mac doesn't offer {model}"
        return True, "busy" if info.get("busy") else "online"
    if provider == "local":
        from .status import on_battery

        if conf.stt.local.skip_on_battery and on_battery():  # also explains a GPU switched off on battery
            return False, "on battery: only if nothing else works"
        if conf.stt.local.device != "cuda":  # cpu/auto: works wherever faster-whisper is installed
            import importlib.util

            installed = importlib.util.find_spec("faster_whisper") is not None
            return installed, ("" if gpu_ok else "on the processor (slower)") if installed else "not installed"
        return gpu_ok, "" if gpu_ok else "no usable NVIDIA GPU"
    return groq_key, "" if groq_key else "GROQ_API_KEY missing"


def test_mac(conf: Config) -> dict[str, Any]:
    """Settings → Mac at home → Test: one /health call (no audio, no model run), uncached."""
    from .providers.mac_whisper import MacUnavailable, MacWhisper

    _mac_cache["at"] = -1e9  # the sidebar and the model list show the fresh state too
    if conf.stt.mac is None:
        return {"ok": False, "detail": "not configured"}
    token = cfgmod.load_keys()["LECTURE_MAC_TOKEN"]
    if not token:
        return {"ok": False, "detail": "LECTURE_MAC_TOKEN missing"}
    stt = MacWhisper(conf, token)
    t0 = time.monotonic()
    try:
        info = stt.health()
    except MacUnavailable as exc:
        return {"ok": False, "detail": str(exc)}
    finally:
        stt.close()
    ms = round((time.monotonic() - t0) * 1000)
    whisper_ok = conf.stt.mac.model in info.get("models", [])
    llm = info.get("llm_models")
    return {"ok": whisper_ok, "ms": ms,
            "whisper": f"{conf.stt.mac.model} {'ready' if whisper_ok else 'missing'}"
                       + (f", {'busy' if info.get('busy') else 'idle'}" if whisper_ok else ""),
            "llm": ("server too old for suggestions" if llm is None else
                    f"{conf.termfix.model} ready" if conf.termfix.model in llm else
                    f"{conf.termfix.model} missing (has {', '.join(llm) or 'nothing'})")}


def termfix_status(conf: Config) -> tuple[bool, str]:
    """(usable, detail) of the term fix suggestions: Ollama on the Mac with termfix.model (from /health)."""
    if not conf.termfix.enabled:
        return False, "off"
    info, error = mac_health(conf)
    if info is None:
        return False, error
    llm = info.get("llm_models")
    if llm is None:
        return False, "the Mac's model server is too old (redeploy mac/server.py)"
    if conf.termfix.model not in llm:
        return False, f"Ollama on the Mac doesn't have {conf.termfix.model}" if llm else "Ollama isn't running on the Mac"
    return True, "online"


def notes_status(conf: Config, entry: str, keys: dict[str, bool], claude: dict) -> tuple[bool, str]:
    """(usable, reason code) of one notes chain entry; the page turns the code into text (i18n r_<code>)."""
    provider = entry.split(":")[0]
    if provider == "custom":
        m = conf.model_entry(entry)
        provider = m.provider
        if provider == "openai":
            if m.key_name and not cfgmod.load_keys().get(m.key_name):
                return False, "custom_nokey"
            return True, "custom"
    if provider == "claude":
        if not claude["installed"]:
            return False, "claude_missing"
        if claude["logged_in"] is False:
            return False, "claude_login"
        return True, "claude_sub"
    if provider in ("gemini", "groq"):
        return (keys[provider], f"{provider}_key" if keys[provider] else f"{provider}_nokey")
    return False, "unsupported"
