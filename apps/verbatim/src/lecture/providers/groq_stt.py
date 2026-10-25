"""Groq Whisper via the OpenAI-compatible API."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import openai
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Config
from ..ratelimit import Ledger, QuotaExhausted, groq_stt_windows
from ..report import NullReporter, Reporter
from .base import Transcription

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
BUCKET = "groq_stt"
TRANSIENT = (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError)


def parse_wait_seconds(headers, message: str) -> float | None:
    """Seconds to wait after a 429: `retry-after` header, else 'try again in 1h2m3.5s' in the message."""
    value = headers.get("retry-after") if headers is not None else None
    if value:
        try:
            return float(value)
        except ValueError:
            pass
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", message or "")
    if m and any(m.groups()):
        h, mins, s = (float(g) if g else 0.0 for g in m.groups())
        return h * 3600 + mins * 60 + s
    return None


class GroqSTT:
    name = "groq"

    def __init__(self, api_key: str, conf: Config, ledger: Ledger, reporter: Reporter | None = None,
                 client: openai.OpenAI | None = None):
        # max_retries=0: tenacity below is the only retry layer (stacked retries burn quota).
        self.client = client or openai.OpenAI(api_key=api_key, base_url=GROQ_BASE_URL, max_retries=0, timeout=300)
        self.conf = conf
        self.ledger = ledger
        self.reporter = reporter or NullReporter()
        self.windows = groq_stt_windows(conf.limits.groq_stt)

    def transcribe(self, audio_path: Path, duration_s: float, language: str, prompt: str,
                   model: str | None = None) -> Transcription:
        tc = self.conf.transcribe
        billed = max(self.conf.limits.groq_stt.min_billed_seconds, duration_s)
        attempts = 0
        for attempt in Retrying(
            stop=stop_after_attempt(tc.max_attempts),
            wait=wait_exponential(multiplier=2, min=2, max=60),
            retry=retry_if_exception_type(TRANSIENT),
            reraise=True,
            before_sleep=lambda rs: self.reporter.warn(
                f"Groq error ({type(rs.outcome.exception()).__name__}), retrying"),
        ):
            with attempt:
                attempts = attempt.retry_state.attempt_number
                # An explicit model is used for every attempt; otherwise switch to the fallback
                # model after repeated failures.
                used = model or (self.conf.stt.model if attempts <= tc.fallback_after_attempts
                                 else self.conf.stt.fallback_model)
                response = self._call_with_quota(audio_path, billed, used, language, prompt)
        return Transcription(response=response, model=used, attempts=attempts)

    def _call_with_quota(self, audio_path: Path, billed: float, model: str, language: str, prompt: str) -> dict:
        max_wait = self.conf.transcribe.max_wait_s
        while True:
            event = self.ledger.reserve(BUCKET, self.windows, {"requests": 1.0, "audio_s": billed},
                                        max_wait, self.reporter, label="Groq")
            try:
                with audio_path.open("rb") as fh:
                    raw = self.client.audio.transcriptions.with_raw_response.create(
                        model=model, file=fh, language=language, prompt=prompt or openai.NOT_GIVEN,
                        temperature=self.conf.transcribe.temperature, response_format="verbose_json",
                        timestamp_granularities=["word", "segment"],
                    )
                return json.loads(raw.text)
            except openai.RateLimitError as exc:
                # The server is the truth: our ledger missed usage (e.g. another app on the same org).
                self.ledger.release(event)
                wait = parse_wait_seconds(exc.response.headers, exc.message) or 60.0
                resume_at = datetime.fromtimestamp(datetime.now().timestamp() + wait)
                if wait > max_wait:
                    raise QuotaExhausted("Groq (server)", resume_at) from exc
                self.reporter.info(f"Groq rate limit (server) — continuing automatically at {resume_at:%H:%M}")
                self.ledger.sleep(wait + 1.0)
            except TRANSIENT:
                # Keep the reservation: after a timeout or 5xx Groq may still have counted the audio.
                raise
            except openai.APIStatusError:
                # 4xx other than 429: not retryable; Groq didn't process the audio.
                self.ledger.release(event)
                raise
