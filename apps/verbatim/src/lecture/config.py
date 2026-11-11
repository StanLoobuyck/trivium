"""Configuration: repo defaults + XDG user overrides + API keys from .env."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Literal

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

APP_NAME = "lecture-transcriber"

# Repo root (the package is installed editable, so the repo defaults stay next to the code).
# LECTURE_HOME overrides it, e.g. for tests.
REPO_DIR = Path(os.environ.get("LECTURE_HOME", Path(__file__).resolve().parents[2]))

KEY_NAMES = ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "LECTURE_MAC_TOKEN", "LECTURE_HUB_CODE")


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP_NAME


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / APP_NAME


def env_path() -> Path:
    return config_dir() / ".env"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Paths(_Strict):
    jobs_dir: Path
    inbox_dir: Path
    # Velox can only save inside Downloads: <this folder>/<course code>/
    downloads_inbox: Path = Field(default=Path("~/Downloads/Verbatim"), validate_default=True)
    latex_dir: Path = Field(default=Path("~/Documents/Lesnotities"), validate_default=True)  # one folder per course

    @field_validator("jobs_dir", "inbox_dir", "downloads_inbox", "latex_dir", mode="after")
    @classmethod
    def _expand(cls, v: Path) -> Path:
        return v.expanduser()


class LocalSttConfig(_Strict):
    model: str
    skip_on_battery: bool = True  # on battery the laptop GPU is only used when nothing else in the chain works
    device: str
    compute_types: list[str]
    beam_size: int
    temperatures: list[float]
    condition_on_previous_text: bool
    vad_filter: bool


class MacSttConfig(_Strict):
    """The model server on the Mac at home (mac/server.py), reached over Tailscale."""
    url: str
    model: str
    health_timeout_s: float = 3.0
    timeout_s: float = 900.0      # ceiling per request; a chunk gets 120 s + half its length (large-v3: ~1 min)
    give_up_after_s: float = 120.0  # Mac stops answering mid-lecture: retry this long, then next provider


class SttConfig(_Strict):
    # built-in providers, or "custom:<id>" = a model the user added in Settings (Config.models)
    providers: list[str]
    model: str
    fallback_model: str
    local: LocalSttConfig
    mac: MacSttConfig | None = None

    @field_validator("providers", mode="after")
    @classmethod
    def _check_providers(cls, v: list[str]) -> list[str]:
        for p in v:
            if p not in ("mac", "local", "groq") and not re.fullmatch(r"custom:[a-z0-9-]+", p):
                raise ValueError(f"stt.providers: '{p}' must be mac, local, groq or custom:<id>")
        if not v or len(set(v)) != len(v):
            raise ValueError("stt.providers must list each provider once")
        return v


class LlmConfig(_Strict):
    tasks: dict[str, list[str]]
    notes_choices: list[str] = Field(default_factory=list)  # selectable in the Setup panel
    openrouter_enabled: bool = False

    @field_validator("tasks", mode="after")
    @classmethod
    def _check_chain(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        for task, chain in v.items():
            for entry in chain:
                provider, _, model = entry.partition(":")
                if provider not in ("claude", "gemini", "groq", "openrouter", "custom") or not model:
                    raise ValueError(f"llm.tasks.{task}: '{entry}' must look like 'gemini:<model>' or 'custom:<id>'")
        return v


class NotesOutputs(_Strict):
    """Optional extras next to notes + summary + transcript (each costs output tokens)."""
    exam_hints: bool = False
    quiz: bool = False
    flashcards: bool = False
    glossary: bool = False


class NotesConfig(_Strict):
    outputs: NotesOutputs = Field(default_factory=NotesOutputs)
    schedule: str
    tonight: str
    max_claude_calls_per_day: int
    study_pack: bool
    timeout_s: float
    max_input_tokens_per_call: int
    ts_tolerance_s: float
    exam_hint_patterns: dict[str, list[str]]

    @field_validator("schedule")
    @classmethod
    def _check_schedule(cls, v: str) -> str:
        import re

        if v != "always" and not re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", v):
            raise ValueError("notes.schedule must be 'always' or 'HH:MM-HH:MM'")
        return v


class GroqSttLimits(_Strict):
    requests_per_minute: int
    requests_per_day: int
    audio_seconds_per_hour: int
    audio_seconds_per_day: int
    max_file_mb: float
    min_billed_seconds: float


class GroqLlmLimits(_Strict):
    requests_per_day: int
    tokens_per_minute: int
    tokens_per_day: int


class GeminiLimits(_Strict):
    requests_per_minute: int
    requests_per_day: int


class Limits(_Strict):
    groq_stt: GroqSttLimits
    groq_llm: GroqLlmLimits
    gemini: GeminiLimits


class SilenceConfig(_Strict):
    frame_s: float
    min_silence_s: float
    floor_percentile: float
    margin_db: float
    min_threshold_db: float
    max_threshold_db: float


class AudioConfig(_Strict):
    filters: str
    silence: SilenceConfig


class ChunkingConfig(_Strict):
    target_s: float = Field(ge=60, le=900)
    search_window_s: float
    skip_silence_over_s: float
    skip_padding_s: float
    min_chunk_s: float
    min_region_s: float
    hard_cut_overlap_s: float
    max_chunk_mb: float
    keep_chunk_audio: bool


class TranscribeConfig(_Strict):
    # lectures the worker transcribes at the same time (the Mac's server has LECTURE_MAC_WORKERS)
    parallel_lectures: int = Field(default=1, ge=1, le=4)
    temperature: float
    previous_tail_words: int
    max_attempts: int
    fallback_after_attempts: int
    max_wait_s: float
    repair_piece_s: float = Field(ge=20, le=300)
    repair_padding_s: float
    masked_max_no_speech: float
    retry_below_logprob: float
    gap_min_s: float


class StitchConfig(_Strict):
    phantom_exact: list[str]
    phantom_prefix: list[str]
    no_speech_prob: float
    no_speech_logprob: float
    compression_ratio: float
    low_confidence_logprob: float
    prompt_echo_ratio: float


class SubtitleConfig(_Strict):
    max_line_chars: int
    max_lines: int
    max_cue_s: float
    min_cue_s: float


class SlidesConfig(_Strict):
    boilerplate_fraction: float = Field(gt=0, le=1)
    boilerplate_min_pages: int


class TermsConfig(_Strict):
    max_terms: int
    rare_zipf: float
    prompt_max_tokens: int = Field(ge=0, le=200)


class TermfixConfig(_Strict):
    """Term fix suggestions by a local LLM on the Mac after transcription (termfix.py)."""
    enabled: bool = True
    model: str = "qwen3.8:27b"   # measured best of 3 (CHANGELOG 2026-10-25); ~6 min per lecture hour
    window_s: float = 300.0      # max length of one part sent to the model
    keep_alive: str = "2m"       # Ollama unloads the model (18 GB) soon after, leaving room for Whisper
    timeout_s: float = 900.0     # one part


class SectionsConfig(_Strict):
    window_s: float = Field(ge=10, le=120)
    next_cost: float
    skip_cost: float
    back_cost: float
    low_confidence: float
    no_slides_min_s: float
    no_slides_max_s: float


class ModelEntry(_Strict):
    """A model the user added in Settings. Chains refer to it as "custom:<id>" (stt.providers, llm.tasks)."""
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    kind: Literal["stt", "notes"]
    # stt: mac (another model on the Mac server) | groq;  notes: claude | gemini | openai (any
    # OpenAI-compatible chat API: Ollama, LM Studio, Groq, OpenRouter, …)
    provider: Literal["mac", "groq", "claude", "gemini", "openai"]
    model: str = Field(min_length=1)
    label: str = ""
    base_url: str | None = None   # openai only
    key_name: str | None = None   # openai only: the .env variable with the API key (none for Ollama)

    @model_validator(mode="after")
    def _check(self) -> "ModelEntry":
        ok = {"stt": ("mac", "groq"), "notes": ("claude", "gemini", "openai")}[self.kind]
        if self.provider not in ok:
            raise ValueError(f"model {self.id}: a {self.kind} model can't use provider {self.provider}")
        if self.provider == "openai" and not self.base_url:
            raise ValueError(f"model {self.id}: an OpenAI-compatible model needs base_url")
        return self


class ArchiveConfig(_Strict):
    # where archived lectures' video/audio copies go: "host:dir" (ssh/rsync; "mac" = ~/.ssh/config alias)
    # or a local directory (tests)
    remote: str = "mac:lecture-archive"


class HubConfig(_Strict):
    url: str = ""  # your own Sequo hub; empty = Verbatim works alone


class AppConfig(_Strict):
    # Simple mode (Windows installer, users without the Mac/hub): hides the Mac, hub, sharing and LaTeX parts
    simple: bool = False


class Config(_Strict):
    app: AppConfig = Field(default_factory=AppConfig)
    hub: HubConfig = Field(default_factory=HubConfig)
    models: list[ModelEntry] = Field(default_factory=list)
    archive: ArchiveConfig = Field(default_factory=ArchiveConfig)
    paths: Paths
    stt: SttConfig
    llm: LlmConfig
    notes: NotesConfig
    limits: Limits
    audio: AudioConfig
    chunking: ChunkingConfig
    transcribe: TranscribeConfig
    slides: SlidesConfig
    terms: TermsConfig
    sections: SectionsConfig
    stitch: StitchConfig
    subtitles: SubtitleConfig
    termfix: TermfixConfig = Field(default_factory=TermfixConfig)

    @model_validator(mode="after")
    def _check_custom_refs(self) -> "Config":
        ids = {m.id: m.kind for m in self.models}
        if len(ids) != len(self.models):
            raise ValueError("models: duplicate ids")
        refs = [("stt", p) for p in self.stt.providers] + [("notes", e) for e in self.llm.tasks.get("notes", [])]
        for kind, entry in refs:
            if entry.startswith("custom:") and ids.get(entry[7:]) != kind:
                raise ValueError(f"'{entry}' doesn't name a {kind} model in models:")
        return self

    def model_entry(self, ref: str) -> ModelEntry:
        """The ModelEntry behind 'custom:<id>'."""
        return next(m for m in self.models if m.id == ref.removeprefix("custom:"))


class Course(_Strict):
    id: str
    name: str
    # timetable codes shared with Sequo and Velox (compared without regard to case)
    codes: list[str] = Field(default_factory=list)
    language: Literal["nl", "en"]
    lecturer: str | None = None
    extra_terms: list[str] = Field(default_factory=list)
    notes_language: Literal["nl", "en"]
    # words Whisper keeps getting wrong in this course → the right spelling ("nent": "NAND"); see fixes.py
    corrections: dict[str, str] = Field(default_factory=dict)
    # "2026-27 S1" (none = from the newest lecture) and archived: true/false (none = automatic, semesters.py)
    semester: str | None = Field(default=None, pattern=r"^\d{4}-\d{2} S[12]$")
    archived: bool | None = None
    # LaTeX notes: false = studied next to the slides (refer, don't copy); true = readable without them
    notes_without_slides: bool = False


def deep_merge(base: dict, override: dict) -> dict:
    """Return base with override merged in; nested dicts merge, everything else replaces."""
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return data


def settings_path() -> Path:
    """Settings changed in the app's Setup panel (written by the app; highest priority)."""
    return config_dir() / "settings.yaml"


def config_files() -> list[Path]:
    """Config files that apply, lowest priority first: repo defaults, the user's own overrides, app settings."""
    files = [REPO_DIR / "config.yaml"]
    for extra in (config_dir() / "config.yaml", settings_path()):
        if extra.exists():
            files.append(extra)
    return files


def load_config() -> Config:
    data: dict = {}
    for path in config_files():
        data = deep_merge(data, _read_yaml(path))
    return Config.model_validate(data)


def courses_file() -> Path:
    user = config_dir() / "courses.yaml"
    return user if user.exists() else REPO_DIR / "courses.yaml"


def load_courses() -> list[Course]:
    path = courses_file()
    courses = [Course.model_validate(c) for c in _read_yaml(path).get("courses", [])]
    ids = [c.id for c in courses]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"{path}: duplicate course ids: {', '.join(sorted(dupes))}")
    return courses


def load_keys() -> dict[str, str]:
    """API keys from the user's .env; real environment variables take precedence."""
    values = dotenv_values(env_path()) if env_path().exists() else {}
    keys = {}
    for name in KEY_NAMES:
        value = os.environ.get(name) or values.get(name) or ""
        keys[name] = value.strip()
    return keys
