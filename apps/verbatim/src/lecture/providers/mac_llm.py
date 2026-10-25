"""A local LLM on the Mac at home: Ollama behind the model server (mac/server.py POST /v1/llm/chat).

Same address and token as the Mac's Whisper (stt.mac). Ollama 0.40.6 from Homebrew has no structured
output (`format` answers 501), so the prompt asks for JSON and chat_json() takes the first object in the answer.
"""

from __future__ import annotations

import json

import httpx

from ..config import Config
from .mac_whisper import MacUnavailable


class MacLlm:
    def __init__(self, conf: Config, token: str, model: str, client: httpx.Client | None = None):
        if conf.stt.mac is None:
            raise MacUnavailable("stt.mac is not configured")
        self.mc = conf.stt.mac
        self.model = model
        self.keep_alive = conf.termfix.keep_alive
        self.client = client or httpx.Client(base_url=self.mc.url, headers={"Authorization": f"Bearer {token}"},
                                             timeout=httpx.Timeout(conf.termfix.timeout_s,
                                                                   connect=self.mc.health_timeout_s))

    def check(self) -> None:
        """Raise MacUnavailable unless the Mac answers and its Ollama has the model."""
        try:
            r = self.client.get("/health", timeout=self.mc.health_timeout_s)
        except httpx.HTTPError as exc:
            raise MacUnavailable(f"Mac at {self.mc.url} not reachable ({type(exc).__name__})") from exc
        if r.status_code != 200:
            raise MacUnavailable(f"Mac health check failed: HTTP {r.status_code}")
        models = r.json().get("llm_models")
        if models is None:
            raise MacUnavailable("the Mac's model server is too old for LLM requests (redeploy mac/server.py)")
        if self.model not in models:
            raise MacUnavailable(f"Ollama on the Mac doesn't have {self.model!r} (has {models or 'nothing: not running?'})")

    def chat_json(self, prompt: str) -> dict:
        body = {"model": self.model, "think": False, "keep_alive": self.keep_alive,
                "options": {"temperature": 0, "num_ctx": 16384},
                "messages": [{"role": "user", "content": prompt}]}
        try:
            r = self.client.post("/v1/llm/chat", json=body)
        except httpx.TransportError as exc:
            raise MacUnavailable(f"Mac stopped answering ({type(exc).__name__})") from exc
        if r.status_code == 503:
            raise MacUnavailable(r.json().get("detail", "Ollama not reachable on the Mac"))
        r.raise_for_status()
        text = r.json()["message"]["content"]
        start = text.find("{")
        if start < 0:
            raise ValueError(f"{self.model}: no JSON in the answer: {text[:200]!r}")
        return json.JSONDecoder().raw_decode(text[start:])[0]

    def close(self) -> None:
        self.client.close()
