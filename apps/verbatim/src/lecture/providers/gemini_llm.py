"""Notes via Google Gemini (free tier: few requests per day, so batches are large and the ledger counts them)."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .. import config as cfgmod
from ..config import Config
from ..ratelimit import DAY_S, Ledger, QuotaExhausted, Window
from ..report import NullReporter, Reporter
from .llm import LLMBadOutput, LLMLimit, LLMResult, LLMUnavailable


def next_pacific_midnight(now: datetime | None = None) -> datetime:
    """Gemini's daily quota resets at midnight Pacific time; returned in local time."""
    pt = (now or datetime.now().astimezone()).astimezone(ZoneInfo("America/Los_Angeles"))
    reset = (pt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return reset.astimezone().replace(tzinfo=None)


class GeminiLLM:
    name = "gemini"

    def __init__(self, conf: Config, model: str, reporter: Reporter | None = None, ledger: Ledger | None = None):
        key = cfgmod.load_keys()["GEMINI_API_KEY"]
        if not key:
            raise LLMUnavailable(f"GEMINI_API_KEY is empty — paste it in {cfgmod.env_path()}")
        from google import genai
        from google.genai import types

        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(conf.notes.timeout_s * 1000)))
        self.conf = conf
        self.model = model
        self.reporter = reporter or NullReporter()
        self.ledger = ledger or Ledger(cfgmod.cache_dir() / "ledger.json")
        lim = conf.limits.gemini
        self.windows = [Window("Gemini requests/min", 60, lim.requests_per_minute, "requests"),
                        Window("Gemini requests/day", DAY_S, lim.requests_per_day, "requests")]

    def generate(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        from google.genai import errors, types

        try:  # waits for the per-minute window; the daily one can't be waited out here
            event = self.ledger.reserve(f"gemini:{self.model}", self.windows, {"requests": 1}, max_wait_s=120,
                                        reporter=self.reporter, label="Gemini")
        except QuotaExhausted as exc:
            raise LLMLimit(str(exc), exc.resume_at) from exc
        t0 = time.time()
        try:
            resp = self.client.models.generate_content(
                model=self.model, contents=user,
                config=types.GenerateContentConfig(system_instruction=system, response_mime_type="application/json",
                                                   response_json_schema=schema, temperature=0.2))
        except errors.APIError as exc:
            from ..doctor import describe_gemini_error

            text = describe_gemini_error(exc)
            if exc.code == 429:
                daily = "PerDay" in text or "per day" in text.lower()
                raise LLMLimit(f"Gemini quota: {text}", next_pacific_midnight() if daily else None) from exc
            if exc.code in (401, 403):
                self.ledger.release(event)
                raise LLMUnavailable(f"Gemini key rejected: {text}") from exc
            raise LLMBadOutput(f"Gemini error: {text}") from exc
        try:
            data = json.loads(_strip_fences(resp.text or ""))
        except json.JSONDecodeError as exc:
            finish = resp.candidates[0].finish_reason if resp.candidates else None
            raise LLMBadOutput(f"Gemini answer is not JSON (finish reason {finish})") from exc
        usage = resp.usage_metadata
        return LLMResult(data=data, model=resp.model_version or self.model,
                         input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                         output_tokens=(usage.candidates_token_count or 0) if usage else 0,
                         elapsed_s=round(time.time() - t0, 1),
                         raw={"finish_reason": str(resp.candidates[0].finish_reason) if resp.candidates else None})


def _strip_fences(text: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
