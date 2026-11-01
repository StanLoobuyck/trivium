"""Whisper on the Mac at home: the model server in mac/server.py, reached over Tailscale (PLAN.md 4b).

The server answers in Groq's verbose_json shape (+ `x_mac`), so stitching, the repair pass, eval and
subtitles work unchanged. Decoding settings are sent with every request: config.yaml stays the only
source. Checking availability is one /health call with a short timeout, so a Mac that is away
power cut) costs ~3 s before the chain moves on, and the laptop's GPU is never touched to find out.

A Mac that stops answering *during* a lecture is retried for stt.mac.give_up_after_s, then transcribe()
raises MacUnavailable and the transcribe stage finishes the remaining chunks on the next provider.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import Config
from ..report import NullReporter, Reporter
from .base import Transcription


_sleep = time.sleep  # tests replace it (tenacity binds its own sleep at import)


class MacUnavailable(RuntimeError):
    """The Mac's model server can't be used now (not configured, not reachable, wrong token)."""


def _transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):  # connection refused/reset, timeouts
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


class MacWhisper:
    name = "mac"
    supports_carry = True  # the server can repeat a prompt on every 30 s window (mac/server.py _install_carry)

    def __init__(self, conf: Config, token: str, reporter: Reporter | None = None,
                 client: httpx.Client | None = None, model: str | None = None):
        if conf.stt.mac is None:
            raise MacUnavailable("stt.mac is not configured")
        self.conf = conf
        self.mc = conf.stt.mac
        self.model = model or self.mc.model  # a model added in Settings may pick another one on the server
        self.reporter = reporter or NullReporter()
        self.client = client or httpx.Client(base_url=self.mc.url, timeout=self._timeout(self.mc.timeout_s),
                                             headers={"Authorization": f"Bearer {token}"})

    def _timeout(self, read_s: float) -> httpx.Timeout:
        # connecting gets the health timeout: a Mac that left Tailscale doesn't refuse, it never answers
        return httpx.Timeout(read_s, connect=self.mc.health_timeout_s)

    @property
    def model_label(self) -> str:
        return f"mac:{self.model}"

    def health(self) -> dict:
        try:
            r = self.client.get("/health", timeout=self.mc.health_timeout_s)
        except httpx.HTTPError as exc:
            raise MacUnavailable(f"Mac at {self.mc.url} not reachable ({type(exc).__name__})") from exc
        if r.status_code == 401:
            raise MacUnavailable("Mac refused the token (LECTURE_MAC_TOKEN differs from the Mac's .env)")
        if r.status_code != 200:
            raise MacUnavailable(f"Mac health check failed: HTTP {r.status_code}")
        return r.json()

    def check(self) -> None:
        """Raise MacUnavailable if the Mac can't transcribe now (used to pick the provider)."""
        info = self.health()
        if self.model not in info.get("models", []):
            raise MacUnavailable(f"Mac doesn't offer model {self.model!r} (has {info.get('models')})")

    def close(self) -> None:
        self.client.close()

    def transcribe(self, audio_path: Path, duration_s: float, language: str, prompt: str,
                   model: str | None = None, carry_prompt: str = "") -> Transcription:
        lc, st = self.conf.stt.local, self.conf.stitch
        data = {
            "model": self.model, "language": language, "prompt": prompt or "",
            "response_format": "verbose_json",
            # same decoding settings as the laptop's local Whisper (minus beam search: mlx-whisper has none)
            "temperature": ",".join(str(t) for t in lc.temperatures),
            "condition_on_previous_text": str(lc.condition_on_previous_text).lower(),
            "compression_ratio_threshold": str(st.compression_ratio),
            "logprob_threshold": str(st.no_speech_logprob),
            "no_speech_threshold": str(st.no_speech_prob),
        }
        if carry_prompt:
            data["carry_prompt"] = carry_prompt
        # the server answers only when done (~1 min per 10 min chunk): a dropped connection shows as silence,
        # so don't wait the full timeout_s for a short clip
        timeout = self._timeout(min(self.mc.timeout_s, 120 + duration_s / 2))
        first_failure: list[float] = []

        def give_up(rs) -> bool:
            first_failure[:] = first_failure or [rs.outcome_timestamp]
            return (rs.attempt_number >= self.conf.transcribe.max_attempts
                    or rs.outcome_timestamp - first_failure[0] >= self.mc.give_up_after_s)

        attempts = 0
        try:
            for attempt in Retrying(
                stop=give_up,
                sleep=lambda s: _sleep(s),
                wait=wait_exponential(multiplier=2, min=2, max=30),
                retry=retry_if_exception(_transient),
                reraise=True,
                before_sleep=lambda rs: self.reporter.warn(
                    f"Mac: {type(rs.outcome.exception()).__name__}, retrying (attempt {rs.attempt_number})"),
            ):
                with attempt:
                    attempts += 1
                    with open(audio_path, "rb") as fh:
                        r = self.client.post("/v1/audio/transcriptions", data=data, timeout=timeout,
                                             files={"file": (audio_path.name, fh, "audio/flac")})
                    if r.status_code == 401:
                        raise MacUnavailable("Mac refused the token")
                    r.raise_for_status()
        except httpx.HTTPError as exc:
            if not _transient(exc):
                raise
            raise MacUnavailable(f"Mac stopped answering ({type(exc).__name__}, {attempts} attempts in "
                                 f"{time.monotonic() - first_failure[0] if first_failure else 0:.0f} s)") from exc
        return Transcription(response=r.json(), model=self.model_label, attempts=attempts)
