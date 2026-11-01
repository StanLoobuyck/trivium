"""Text LLM interface for notes: structured JSON in, structured JSON out. Pipeline code only talks to this."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass
class LLMResult:
    data: dict[str, Any]          # parsed structured output
    model: str                    # model that answered (resolved name when the provider reports it)
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)  # provider response metadata, saved with the batch


class LLMUnavailable(RuntimeError):
    """This provider can't be used at all right now (not logged in, no key, CLI missing) → next provider."""


class LLMLimit(RuntimeError):
    """Budget/schedule/usage limit: try again later (resume_at) or use the next provider."""

    def __init__(self, message: str, resume_at: datetime | None = None):
        super().__init__(message)
        self.resume_at = resume_at


class LLMBadOutput(RuntimeError):
    """The call worked but the answer isn't usable (no JSON, schema mismatch)."""


class LLMProvider(Protocol):
    name: str

    def generate(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult: ...


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Pydantic's JSON schema with $defs/$ref resolved inline (not every structured-output API follows $ref)."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            # drop pydantic's "title" annotations (strings), not properties that happen to be called "title"
            return {k: walk(v) for k, v in node.items() if k != "$defs" and not (k == "title" and isinstance(v, str))}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)
