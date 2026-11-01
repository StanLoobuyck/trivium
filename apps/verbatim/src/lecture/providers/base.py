"""Provider interfaces. Pipeline code only talks to these."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class Transcription:
    response: dict[str, Any]   # the provider's verbose_json response, unmodified
    model: str                 # model that produced it (may be the fallback)
    attempts: int


class STTProvider(Protocol):
    def transcribe(self, audio_path: Path, duration_s: float, language: str, prompt: str,
                   model: str | None = None) -> Transcription: ...
