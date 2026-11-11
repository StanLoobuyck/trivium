"""`lecture doctor`: check tools, config, API keys, live models and quotas."""

from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import config as cfg
from .util import find_claude

Status = Literal["ok", "warn", "fail", "info"]
ICONS = {"ok": "✅", "warn": "⚠️ ", "fail": "❌", "info": "ℹ️ "}

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
TIMEOUT_S = 60.0


@dataclass
class Check:
    name: str
    status: Status
    detail: str = ""


def _version_line(binary: str) -> str:
    out = subprocess.run([binary, "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
    return out.stdout.splitlines()[0] if out.stdout else "unknown version"


def check_tools() -> Iterator[Check]:
    missing = []
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary):
            yield Check(binary, "ok", _version_line(binary))
        else:
            missing.append("ffmpeg")
            yield Check(binary, "fail", "not found")
    optional = {
        "notify-send": ("libnotify", "desktop notifications"),
        "soffice": ("libreoffice-fresh", "PPTX → images for slide alignment"),
        "pandoc": ("pandoc-cli", "export notes to .docx/.pdf"),
    }
    for binary, (package, purpose) in optional.items():
        if shutil.which(binary):
            yield Check(binary, "ok", purpose)
        else:
            yield Check(binary, "info", f"optional, not installed ({purpose}) — package: {package}")
    if missing:
        yield Check("install", "fail", "run: sudo pacman -S --needed ffmpeg")


def check_python() -> Iterator[Check]:
    v = sys.version_info
    version = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) == (3, 12):
        yield Check("python", "ok", f"{version} ({sys.prefix})")
    else:
        yield Check("python", "warn", f"{version}; project is pinned to 3.12 — run `uv sync`")
    if sys.prefix == sys.base_prefix:
        yield Check("venv", "fail", "not running inside the project venv — use `uv run lecture …`")


def check_config() -> Iterator[Check]:
    try:
        conf = cfg.load_config()
        files = ", ".join(str(p) for p in cfg.config_files())
        yield Check("config.yaml", "ok", files)
    except Exception as exc:  # noqa: BLE001 — report any parse/validation error
        yield Check("config.yaml", "fail", str(exc))
        return
    try:
        courses = cfg.load_courses()
        yield Check("courses.yaml", "ok", f"{len(courses)} courses ({cfg.courses_file()})")
    except Exception as exc:  # noqa: BLE001
        yield Check("courses.yaml", "fail", str(exc))
    yield Check("jobs dir", "info", str(conf.paths.jobs_dir))


def check_gpu(conf: cfg.Config, calls: bool) -> Iterator[Check]:
    """Local Whisper readiness: NVIDIA GPU, faster-whisper extra, CUDA libraries, optional tiny transcription."""
    if "local" not in conf.stt.providers:
        yield Check("local whisper", "info", "not in stt.providers")
        return
    if not shutil.which("nvidia-smi"):
        yield Check("gpu", "warn", "nvidia-smi not found — local Whisper unavailable, Groq will be used")
        return
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.used,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    if out.returncode != 0:
        from .status import nvidia_smi_problem

        yield Check("gpu", "warn", nvidia_smi_problem(out.stdout + out.stderr))
        return
    yield Check("gpu", "ok", out.stdout.strip().splitlines()[0])
    try:
        from .providers.local_whisper import LocalUnavailable, LocalWhisper, preload_cuda_libraries
        preload_cuda_libraries()
        import ctranslate2
    except ImportError:
        yield Check("local whisper", "warn", "faster-whisper not installed — run scripts/install.sh (extra 'local')")
        return
    except OSError as exc:
        yield Check("local whisper", "warn", f"CUDA libraries failed to load: {exc}")
        return
    if ctranslate2.get_cuda_device_count() < 1:
        yield Check("local whisper", "warn", "CTranslate2 sees no CUDA device — Groq will be used")
        return
    if not calls:
        yield Check("local whisper", "ok", f"ctranslate2 {ctranslate2.__version__}, CUDA device found")
        return
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "tone.flac"
        _tiny_audio(audio)
        try:
            lw = LocalWhisper(conf)
            t = lw.transcribe(audio, 1.0, "nl", "")
            x = t.response["x_local"]
            yield Check("local whisper", "ok", f"{conf.stt.local.model} ({x['compute_type']}) transcribed a test "
                        f"tone in {x['elapsed_s']} s")
        except LocalUnavailable as exc:
            yield Check("local whisper", "warn", f"{exc} — Groq will be used")
        except Exception as exc:  # noqa: BLE001 — report anything the GPU stack throws
            yield Check("local whisper", "warn", f"test transcription failed: {exc} — Groq will be used")


def check_claude_cli(conf: cfg.Config) -> Iterator[Check]:
    """Notes via Claude Code headless (`claude -p`). Login/limits are checked when notes run (Phase 5)."""
    if not any(m.startswith("claude:") for chain in conf.llm.tasks.values() for m in chain):
        return
    path = find_claude()
    if not path:
        yield Check("claude cli", "warn", "`claude` not found — notes will use the next provider (Gemini)")
        return
    out = subprocess.run([path, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    yield Check("claude cli", "ok" if out.returncode == 0 else "warn", (out.stdout or out.stderr).strip()[:80])


def check_env_file() -> Iterator[Check]:
    path = cfg.env_path()
    if not path.exists():
        yield Check(".env", "fail", f"{path} missing — run scripts/install.sh")
        return
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        yield Check(".env", "warn", f"{path} is readable by others (mode {mode:o}) — run: chmod 600 {path}")
    else:
        yield Check(".env", "ok", str(path))


def _ratelimit_headers(headers) -> str:
    found = {k.lower(): v for k, v in headers.items() if k.lower().startswith("x-ratelimit-")}
    if not found:
        return "no rate-limit headers"
    return ", ".join(f"{k.removeprefix('x-ratelimit-')}={v}" for k, v in sorted(found.items()))


def _tiny_audio(path: Path) -> None:
    """1 s of a quiet tone as 16 kHz mono FLAC (billed as Groq's 10 s minimum)."""
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=1", "-af", "volume=0.1",
         "-ac", "1", "-ar", "16000", "-c:a", "flac", str(path)],
        check=True, timeout=30,
    )


def check_groq(key: str, conf: cfg.Config, calls: bool) -> Iterator[Check]:
    if not key:
        yield Check("groq key", "fail", f"GROQ_API_KEY empty — create one at console.groq.com/keys and paste it in {cfg.env_path()}")
        return
    import openai

    client = openai.OpenAI(api_key=key, base_url=GROQ_BASE_URL, max_retries=0, timeout=TIMEOUT_S)
    try:
        ids = sorted(m.id for m in client.models.list())
    except openai.AuthenticationError:
        yield Check("groq key", "fail", "rejected (401) — check the key in .env")
        return
    except openai.APIError as exc:
        yield Check("groq key", "fail", f"model list failed: {exc}")
        return
    yield Check("groq key", "ok", "accepted")

    whisper = [m for m in ids if "whisper" in m]
    llms = [m for m in ids if "whisper" not in m]
    yield Check("groq whisper models", "info", ", ".join(whisper) or "none")
    yield Check("groq LLM models", "info", ", ".join(llms) or "none")
    for model in (conf.stt.model, conf.stt.fallback_model):
        if model not in ids:
            yield Check(f"groq {model}", "fail", "configured in config.yaml but not available — update stt.*")
    groq_llms = {m.split(":", 1)[1] for chain in conf.llm.tasks.values() for m in chain if m.startswith("groq:")}
    for model in sorted(groq_llms - set(ids)):
        yield Check(f"groq {model}", "warn", "in llm.tasks but not available — update config.yaml")

    if not calls:
        return
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "tone.flac"
        _tiny_audio(audio)
        try:
            with audio.open("rb") as fh:
                raw = client.audio.transcriptions.with_raw_response.create(
                    model=conf.stt.model, file=fh, language="nl", temperature=0,
                    response_format="verbose_json", timestamp_granularities=["word", "segment"],
                )
            raw.parse()
            yield Check(f"groq STT call ({conf.stt.model})", "ok", _ratelimit_headers(raw.headers))
        except openai.RateLimitError as exc:
            yield Check(f"groq STT call ({conf.stt.model})", "warn", f"rate limited: {exc.message}")
        except openai.APIError as exc:
            yield Check(f"groq STT call ({conf.stt.model})", "fail", str(exc))

    for model in sorted(groq_llms & set(ids)):
        try:
            raw = client.chat.completions.with_raw_response.create(
                model=model, messages=[{"role": "user", "content": "Reply with the single word OK."}],
                max_completion_tokens=200,
            )
            raw.parse()
            yield Check(f"groq LLM call ({model})", "ok", _ratelimit_headers(raw.headers))
        except openai.RateLimitError as exc:
            yield Check(f"groq LLM call ({model})", "warn", f"rate limited: {exc.message}")
        except openai.APIError as exc:
            yield Check(f"groq LLM call ({model})", "fail", str(exc))


def describe_gemini_error(exc) -> str:
    """Turn a google-genai APIError into one readable line, incl. quota id/limit and retry delay."""
    parts = [f"{exc.code} {exc.status or ''}".strip(), (exc.message or "").split("\n")[0]]
    details = exc.details.get("error", {}).get("details", []) if isinstance(exc.details, dict) else []
    for d in details:
        kind = d.get("@type", "")
        if kind.endswith("QuotaFailure"):
            for v in d.get("violations", []):
                parts.append(f"quota {v.get('quotaId', '?')} = {v.get('quotaValue', '?')}")
        elif kind.endswith("RetryInfo"):
            parts.append(f"retry after {d.get('retryDelay', '?')}")
    if "location is not supported" in (exc.message or "").lower():
        parts.append("Gemini free tier is not available from this location → Groq fallback will be used")
    return " — ".join(p for p in parts if p)


def check_gemini(key: str, conf: cfg.Config, calls: bool) -> Iterator[Check]:
    if not key:
        yield Check("gemini key", "fail", "GEMINI_API_KEY empty — create one at aistudio.google.com/apikey "
                    f"(personal Google account) and paste it in {cfg.env_path()}")
        return
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(TIMEOUT_S * 1000)))
    try:
        models = list(client.models.list())
    except errors.APIError as exc:
        yield Check("gemini key", "fail", describe_gemini_error(exc))
        return
    yield Check("gemini key", "ok", "accepted")

    names = {m.name.removeprefix("models/") for m in models if "generateContent" in (m.supported_actions or [])}
    flash = sorted(n for n in names if "flash" in n)
    yield Check("gemini Flash models", "info", ", ".join(flash) or "none")
    gemini_llms = {m.split(":", 1)[1] for chain in conf.llm.tasks.values() for m in chain if m.startswith("gemini:")}
    for model in sorted(gemini_llms - names):
        yield Check(f"gemini {model}", "warn", "in llm.tasks but not listed — update config.yaml")

    lim = conf.limits.gemini
    yield Check("gemini quota", "info",
                f"configured: {lim.requests_per_day} requests/day, {lim.requests_per_minute}/min "
                "(Google doesn't expose this via the API; re-check aistudio.google.com/rate-limit occasionally)")
    if not calls:
        return
    for model in sorted(gemini_llms & names):
        try:
            resp = client.models.generate_content(model=model, contents="Reply with the single word OK.")
            usage = resp.usage_metadata
            tokens = f"{usage.prompt_token_count} in / {usage.candidates_token_count} out" if usage else ""
            yield Check(f"gemini call ({model})", "ok", f"answered {resp.text.strip()[:20]!r} {tokens}".strip())
        except errors.APIError as exc:
            status: Status = "warn" if exc.code == 429 else "fail"
            yield Check(f"gemini call ({model})", status, describe_gemini_error(exc))


def check_openrouter(key: str, conf: cfg.Config) -> Iterator[Check]:
    if not key:
        status: Status = "warn" if conf.llm.openrouter_enabled else "info"
        yield Check("openrouter key", status, "not set (optional fallback)")
        return
    import httpx

    try:
        r = httpx.get(OPENROUTER_KEY_URL, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        yield Check("openrouter key", "fail", f"request failed: {exc}")
        return
    if r.status_code == 200:
        data = r.json().get("data", {})
        yield Check("openrouter key", "ok", f"free tier: {data.get('is_free_tier')}, limit: {data.get('limit')}")
    else:
        yield Check("openrouter key", "fail", f"HTTP {r.status_code}: {r.text[:200]}")


def check_mac(token: str, conf: cfg.Config, calls: bool) -> Iterator[Check]:
    """The model server on the Mac at home: reachable, token accepted, model offered, optional 2 s test."""
    if "mac" not in conf.stt.providers or conf.stt.mac is None:
        yield Check("mac whisper", "info", "not in stt.providers")
        return
    if not token:
        yield Check("mac whisper", "warn", f"LECTURE_MAC_TOKEN missing in {cfg.env_path()} — the Mac is skipped")
        return
    import time

    from .providers.mac_whisper import MacUnavailable, MacWhisper

    stt = MacWhisper(conf, token)
    try:
        t0 = time.monotonic()
        info = stt.health()
        ms = (time.monotonic() - t0) * 1000
        status = "ok" if conf.stt.mac.model in info.get("models", []) else "fail"
        yield Check("mac whisper", status, f"{conf.stt.mac.url}: {info.get('mlx_whisper')} (mlx {info.get('mlx')}), "
                    f"model {conf.stt.mac.model}, {'busy' if info.get('busy') else 'idle'}, {ms:.0f} ms")
        if conf.termfix.enabled:
            llm = info.get("llm_models")
            tf_ok = bool(llm) and conf.termfix.model in llm
            yield Check("mac llm", "ok" if tf_ok else "warn",
                        f"Ollama {conf.termfix.model} ready (term suggestions)" if tf_ok
                        else "model server too old (redeploy mac/server.py)" if llm is None
                        else f"Ollama has {llm or 'nothing (not running?)'}, not {conf.termfix.model} — suggestions skipped")
        if calls and status == "ok":
            with tempfile.TemporaryDirectory() as tmp:
                clip = Path(tmp) / "tone.flac"
                subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                                "sine=frequency=440:duration=2", "-ac", "1", "-ar", "16000", str(clip)], check=True)
                t0 = time.monotonic()
                stt.transcribe(clip, 2.0, "nl", "")
                yield Check("mac whisper test", "ok", f"2 s clip round trip {time.monotonic() - t0:.1f} s")
    except MacUnavailable as exc:
        yield Check("mac whisper", "warn", f"{exc} — the laptop GPU / Groq will be used")
    except Exception as exc:  # noqa: BLE001
        yield Check("mac whisper test", "fail", str(exc))
    finally:
        stt.close()


def run_doctor(online: bool = True, calls: bool = True) -> list[Check]:
    """Run all checks. online=False skips network; calls=False lists models but makes no test calls."""
    checks: list[Check] = []
    checks += check_tools()
    checks += check_python()
    checks += check_config()
    checks += check_env_file()
    try:
        conf = cfg.load_config()
    except Exception:  # noqa: BLE001 — already reported by check_config
        return checks
    # GPU and Claude CLI checks are local, so they also run with --offline.
    checks += check_gpu(conf, calls)
    checks += check_claude_cli(conf)
    if not online:
        return checks
    keys = cfg.load_keys()
    checks += check_mac(keys["LECTURE_MAC_TOKEN"], conf, calls)
    checks += check_groq(keys["GROQ_API_KEY"], conf, calls)
    checks += check_gemini(keys["GEMINI_API_KEY"], conf, calls)
    checks += check_openrouter(keys["OPENROUTER_API_KEY"], conf)
    return checks
