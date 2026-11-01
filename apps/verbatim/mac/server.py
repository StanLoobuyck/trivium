"""Lecture Transcriber model server for the Mac at home (PLAN.md section 4b).

Speaks the OpenAI/Groq transcription API (POST /v1/audio/transcriptions, multipart) and answers in Groq's
verbose_json shape, so the laptop's pipeline treats it like any other STT provider. POST /v1/llm/chat passes
an Ollama /api/chat request to Ollama on this Mac (brew service, localhost only), behind the same token. Decoding settings come
with each request (the laptop's config.yaml is the single source). Only listens on the Tailscale address
and needs a bearer token.

    uv run python server.py            # settings from .env next to this file
"""

from __future__ import annotations

import asyncio
import os
import secrets
import shutil
import subprocess
import tempfile
import multiprocessing
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from importlib.metadata import version
from pathlib import Path

import httpx
from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

HERE = Path(__file__).resolve().parent
# Short names the laptop sends → MLX weights on Hugging Face (downloaded once to ~/.cache/huggingface)
MODELS = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


load_env(HERE / ".env")
TOKEN = os.environ.get("LECTURE_MAC_TOKEN", "")
DEFAULT_MODEL = os.environ.get("LECTURE_MAC_MODEL", "large-v3")
OLLAMA = os.environ.get("LECTURE_MAC_OLLAMA", "http://127.0.0.1:11434")

# Parallel transcriptions: separate worker processes, each with its own model in memory (~4.2 GB for large-v3).
# Measured 2026-10-20 on the M1 Max: 2 at once ≈ 1.5× the throughput of 1; 3–4 at once is slower again.
WORKERS = max(1, int(os.environ.get("LECTURE_MAC_WORKERS", "1")))

app = FastAPI(title="lecture-models")
bearer = HTTPBearer(auto_error=False)
# processes, not threads: MLX streams are per thread and mlx-whisper caches its model in a module global;
# each process keeps its model loaded between requests
pool = ProcessPoolExecutor(max_workers=WORKERS, mp_context=multiprocessing.get_context("spawn"))
state = {"loaded": None, "busy": 0, "waiting": 0, "served": 0}
state_lock = threading.Lock()


def check_token(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    if not TOKEN or cred is None or not secrets.compare_digest(cred.credentials, TOKEN):
        raise HTTPException(status_code=401, detail="missing or wrong token")


_carry: dict = {"text": "", "tokens": None}  # per worker process; a process runs one transcription at a time


def _install_carry() -> None:
    """Repeat a prompt on every 30 s window (openai-whisper's carry_initial_prompt; mlx-whisper 0.4.3 lacks it).

    With condition_on_previous_text off, mlx-whisper (like faster-whisper) clears the prompt after the first
    window, so the term list only reaches the first 30 s of a request. This wraps the model's decode step:
    a window whose prompt doesn't start with the carried tokens gets them in front, keeping the most recent
    previous-text tokens that still fit Whisper's prompt limit (n_text_ctx // 2 - 1 = 223 tokens).
    """
    import dataclasses

    from mlx_whisper import whisper as mw
    from mlx_whisper.tokenizer import get_tokenizer

    if getattr(mw.Whisper.decode, "_carry", False):
        return
    original = mw.Whisper.decode

    def decode(self, mel, options=None, **kw):
        if options is not None and _carry["text"]:
            if _carry["tokens"] is None:
                tok = get_tokenizer(self.is_multilingual, num_languages=self.num_languages,
                                    language=options.language, task=options.task)
                _carry["tokens"] = tok.encode(" " + _carry["text"].strip())
            carried, prompt = _carry["tokens"], list(options.prompt or [])
            if carried and prompt[:len(carried)] != carried:
                room = self.dims.n_text_ctx // 2 - 1 - len(carried)
                options = dataclasses.replace(options, prompt=carried + (prompt[-room:] if room > 0 and prompt else []))
        return original(self, mel, options, **kw) if options is not None else original(self, mel, **kw)

    decode._carry = True
    mw.Whisper.decode = decode


def _run(path: str, repo: str, kwargs: dict, carry_prompt: str = "") -> dict:
    """Runs in a worker process."""
    import mlx_whisper

    _install_carry()
    _carry.update(text=carry_prompt, tokens=None)
    t0 = time.perf_counter()
    try:
        result = mlx_whisper.transcribe(path, path_or_hf_repo=repo, **kwargs)
    finally:
        _carry.update(text="", tokens=None)
    return {"result": result, "elapsed": time.perf_counter() - t0}


def duration_s(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True)
    return float(out.stdout)


def to_verbose_json(result: dict, duration: float, model: str, elapsed: float) -> dict:
    """mlx-whisper output → Groq verbose_json (+ x_mac), same fields as providers/local_whisper.py."""
    segs, words = [], []
    for i, s in enumerate(result["segments"]):
        segs.append({
            "id": i, "start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3), "text": s["text"],
            "avg_logprob": float(s["avg_logprob"]), "no_speech_prob": float(s["no_speech_prob"]),
            "compression_ratio": float(s["compression_ratio"]), "temperature": float(s["temperature"]),
        })
        words += [{"word": w["word"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)}
                  for w in s.get("words") or []]
    return {
        "task": "transcribe", "language": result.get("language"), "duration": duration,
        "text": "".join(s["text"] for s in segs), "segments": segs, "words": words,
        "x_mac": {"model": model, "engine": f"mlx-whisper {version('mlx-whisper')}", "beam_size": None,
                  "elapsed_s": round(elapsed, 2),
                  "realtime_factor": round(duration / elapsed, 1) if elapsed > 0 else None},
    }


def llm_models() -> list[str]:
    try:
        r = httpx.get(f"{OLLAMA}/api/tags", timeout=1.0)
        r.raise_for_status()
        return sorted(m["name"] for m in r.json()["models"])
    except (httpx.HTTPError, KeyError, ValueError):
        return []  # Ollama not running: STT still works


@app.get("/health", dependencies=[Depends(check_token)])
def health() -> dict:
    return {"ok": True, "models": sorted(MODELS), "default_model": DEFAULT_MODEL, "loaded": state["loaded"],
            "workers": WORKERS, "busy": state["busy"] >= WORKERS, "running": state["busy"],
            "waiting": state["waiting"], "served": state["served"],
            "mlx_whisper": version("mlx-whisper"), "mlx": version("mlx"), "llm_models": llm_models()}


@app.post("/v1/llm/chat", dependencies=[Depends(check_token)])
async def llm_chat(body: dict = Body(...)) -> dict:
    """Ollama /api/chat, non-streaming. Ollama 0.40.6 from Homebrew has no structured output (`format`
    answers 501: libollama_xgrammar missing), so callers ask for JSON in the prompt."""
    body = {**body, "stream": False}
    async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=3.0)) as client:
        try:
            r = await client.post(f"{OLLAMA}/api/chat", json=body)
        except httpx.TransportError as exc:
            raise HTTPException(status_code=503, detail=f"Ollama not reachable on the Mac ({type(exc).__name__})")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.post("/v1/audio/transcriptions", dependencies=[Depends(check_token)])
async def transcriptions(
    file: UploadFile = File(...),
    model: str = Form(""),
    language: str = Form(""),
    prompt: str = Form(""),
    response_format: str = Form("verbose_json"),
    temperature: str = Form("0"),  # one value (OpenAI API) or a comma list = fallback ladder
    condition_on_previous_text: bool = Form(False),
    compression_ratio_threshold: float | None = Form(None),
    logprob_threshold: float | None = Form(None),
    no_speech_threshold: float | None = Form(None),
    carry_prompt: str = Form(""),  # repeated on every 30 s window after the first (which uses `prompt`)
) -> dict:
    name = model or DEFAULT_MODEL
    if name not in MODELS:
        raise HTTPException(status_code=400, detail=f"unknown model {name!r}; known: {sorted(MODELS)}")
    if response_format != "verbose_json":
        raise HTTPException(status_code=400, detail="only response_format=verbose_json is supported")
    temps = tuple(float(t) for t in temperature.split(",") if t.strip()) or (0.0,)
    kwargs = {"language": language or None, "initial_prompt": prompt or None, "word_timestamps": True,
              "temperature": temps if len(temps) > 1 else temps[0],
              "condition_on_previous_text": condition_on_previous_text, "verbose": None}
    for key, value in (("compression_ratio_threshold", compression_ratio_threshold),
                       ("logprob_threshold", logprob_threshold), ("no_speech_threshold", no_speech_threshold)):
        if value is not None:
            kwargs[key] = value

    suffix = Path(file.filename or "audio.flac").suffix or ".flac"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
    try:
        duration = duration_s(tmp.name)
        with state_lock:
            state["waiting"] += 1
        future = pool.submit(_run, tmp.name, MODELS[name], kwargs, carry_prompt)
        with state_lock:  # counted as running from submission; the pool queues beyond WORKERS
            state["waiting"] -= 1
            state["busy"] += 1
        try:
            out = await asyncio.wrap_future(future)
        finally:
            with state_lock:
                state["busy"] -= 1
    finally:
        os.unlink(tmp.name)
    state["served"] += 1
    state["loaded"] = MODELS[name]
    response = to_verbose_json(out["result"], duration, name, out["elapsed"])
    response["x_mac"]["carry_prompt"] = bool(carry_prompt)
    return response


def main() -> None:
    import uvicorn

    host = os.environ.get("LECTURE_MAC_HOST", "")
    if not TOKEN or not host:
        raise SystemExit("set LECTURE_MAC_TOKEN and LECTURE_MAC_HOST (the Tailscale IP) in .env")
    uvicorn.run(app, host=host, port=int(os.environ.get("LECTURE_MAC_PORT", "7862")), log_level="info")


if __name__ == "__main__":
    main()
