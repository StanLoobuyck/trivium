"""Notes via any OpenAI-compatible chat API: Ollama (e.g. on the Mac at home), LM Studio, Groq, OpenRouter, …

Used for models the user adds in Settings (config `models:` with provider "openai"). Structured output via
`response_format` json_schema; servers that ignore it still get the schema in the system prompt, and the
answer is checked by s7_notes like any other provider's.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import openai

from .. import config as cfgmod
from ..config import Config, ModelEntry
from ..report import NullReporter, Reporter
from .llm import LLMBadOutput, LLMLimit, LLMResult, LLMUnavailable


class OpenAICompatLLM:
    name = "openai"

    def __init__(self, conf: Config, entry: ModelEntry, reporter: Reporter | None = None,
                 client: openai.OpenAI | None = None):
        key = cfgmod.load_keys().get(entry.key_name, "") if entry.key_name else "none"  # Ollama ignores the key
        if entry.key_name and not key:
            raise LLMUnavailable(f"{entry.key_name} is empty — add it in Settings › Keys")
        self.entry = entry
        self.model = entry.model
        self.reporter = reporter or NullReporter()
        self.client = client or openai.OpenAI(base_url=entry.base_url, api_key=key, max_retries=0,
                                              timeout=conf.notes.timeout_s)

    def generate(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        t0 = time.time()
        system = system + "\n\nAnswer with one JSON object that follows this JSON schema:\n" + json.dumps(schema)
        try:
            resp = self.client.chat.completions.create(
                model=self.model, temperature=0.2,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_schema", "json_schema": {"name": "notes", "schema": schema}})
        except openai.APIConnectionError as exc:
            raise LLMUnavailable(f"{self.entry.base_url} not reachable ({exc.__class__.__name__})") from exc
        except openai.AuthenticationError as exc:
            raise LLMUnavailable(f"key rejected by {self.entry.base_url}") from exc
        except openai.RateLimitError as exc:
            raise LLMLimit(f"rate limit at {self.entry.base_url}: {exc}") from exc
        except openai.APIError as exc:
            raise LLMBadOutput(f"{self.entry.base_url}: {exc}") from exc
        text = resp.choices[0].message.content or ""
        try:
            data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip()))
        except json.JSONDecodeError as exc:
            raise LLMBadOutput(f"answer is not JSON (finish reason {resp.choices[0].finish_reason})") from exc
        usage = resp.usage
        return LLMResult(data=data, model=resp.model or self.model,
                         input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                         output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                         elapsed_s=round(time.time() - t0, 1), raw={"finish_reason": resp.choices[0].finish_reason})
