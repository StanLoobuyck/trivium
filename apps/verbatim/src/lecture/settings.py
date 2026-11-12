"""Changes made in the app's Setup panel: models, outputs, API keys, courses, folders.

App settings go to settings.yaml (highest priority, see config.config_files), never into the user's own
config.yaml. Keys go into the existing .env with python-dotenv (comments kept, chmod 600) and are never
sent back to the browser — only whether each is set. Courses: the first edit copies the list to the user's
courses.yaml. Every write is validated by loading the result; a bad change is rolled back.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from . import config as cfgmod
from .config import Course
from .util import find_claude, read_json, write_json, write_text

STT_MODES = {"mac": ["mac", "local", "groq"], "local": ["local", "groq"], "cloud": ["groq"]}
# API keys of AI providers (Settings › Connections, and the "Add a model" form): name → (.env name, label, where
# to get one). A model on another OpenAI-compatible server keeps its key under its own name (models.add_model).
PROVIDER_KEYS = {
    "groq": ("GROQ_API_KEY", "Groq", "https://console.groq.com/keys"),
    "gemini": ("GEMINI_API_KEY", "Gemini", "https://aistudio.google.com/apikey"),
    "openai": ("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys"),
    "anthropic": ("ANTHROPIC_API_KEY", "Anthropic", "https://console.anthropic.com/settings/keys"),
    "mistral": ("MISTRAL_API_KEY", "Mistral", "https://console.mistral.ai/api-keys"),
    "openrouter": ("OPENROUTER_API_KEY", "OpenRouter", "https://openrouter.ai/keys"),
}
KEY_FIELDS = {**{name: env for name, (env, _, _) in PROVIDER_KEYS.items()},
              "mac": "LECTURE_MAC_TOKEN", "hub": "LECTURE_HUB_CODE"}
GEMINI_NOTES = "gemini:gemini-3.8-flash"  # added to the notes models when a Gemini key is saved


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}


def _write_validated(path: Path, data: dict, check) -> None:
    before = path.read_text(encoding="utf-8") if path.exists() else None
    write_text(path, "# Written by the Lecture Transcriber Setup panel. Edit there, or delete to reset.\n"
               + yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    try:
        check()
    except Exception:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            write_text(path, before)
        raise


def update_settings(patch: dict[str, Any]) -> None:
    """Deep-merge a patch into settings.yaml (validated)."""
    path = cfgmod.settings_path()
    _write_validated(path, cfgmod.deep_merge(_read(path), patch), cfgmod.load_config)


def set_notes_model(choice: str) -> None:
    conf = cfgmod.load_config()
    choices = conf.llm.notes_choices
    if choice not in choices:
        raise ValueError(f"unknown notes model {choice!r}")
    # chosen first, then one fallback per *other* provider: when Claude's limit is hit, Haiku shares it,
    # so the useful fallback for Sonnet is Gemini (then Groq), not Haiku
    family = lambda entry: entry.split(":", 1)[0]  # noqa: E731
    chain, seen = [choice], {family(choice)}
    for entry in dict.fromkeys([*choices, *conf.llm.tasks["notes"]]):
        if family(entry) not in seen:
            chain.append(entry)
            seen.add(family(entry))
    update_settings({"llm": {"tasks": {"notes": chain}}})


def set_stt_mode(mode: str) -> None:
    if mode not in STT_MODES:
        raise ValueError(f"unknown speech-to-text mode {mode!r}")
    update_settings({"stt": {"providers": STT_MODES[mode]}})


def set_skip_on_battery(value: bool) -> None:
    update_settings({"stt": {"local": {"skip_on_battery": bool(value)}}})


def set_mac_url(url: str) -> str:
    """The Mac's model server address (stt.mac.url), e.g. http://my-mac:7862 (Tailscale name)."""
    url = url.strip().rstrip("/")
    if not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?", url):
        raise ValueError("give an address like http://my-mac:7862")
    update_settings({"stt": {"mac": {"url": url}}})
    return url


def set_hub_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and not re.fullmatch(r"https?://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~/-]*)?", url):
        raise ValueError("give an address like https://my-mac.example.ts.net")
    update_settings({"hub": {"url": url}})
    return url


def set_outputs(outputs: dict[str, bool]) -> None:
    allowed = {"exam_hints", "quiz", "flashcards", "glossary"}
    if set(outputs) - allowed:
        raise ValueError(f"unknown outputs: {', '.join(set(outputs) - allowed)}")
    update_settings({"notes": {"outputs": {k: bool(v) for k, v in outputs.items()}}})


# --- API keys ----------------------------------------------------------------------------------------------


def key_status() -> dict[str, bool]:
    keys = cfgmod.load_keys()
    return {name: bool(keys[env]) for name, env in KEY_FIELDS.items()}


def _env_name(name: str) -> str:
    """'gemini' → GEMINI_API_KEY; a model's own key ('LMSTUDIO_API_KEY') stays as it is."""
    if name in KEY_FIELDS:
        return KEY_FIELDS[name]
    if cfgmod._OWN_KEY.fullmatch(name):
        return name
    raise ValueError(f"unknown key {name!r}")


def set_key(name: str, value: str, add_models: bool = True) -> None:
    """Save an API key in .env. add_models=False: the caller adds the model itself (the "Add a model" form)."""
    from dotenv import set_key as dotenv_set

    env = _env_name(name)
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-.]{10,200}", value):
        raise ValueError("that doesn't look like an API key")
    path = cfgmod.env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    dotenv_set(str(path), env, value, quote_mode="never")
    path.chmod(0o600)
    if env == "GEMINI_API_KEY" and add_models:
        add_gemini_notes()


def remove_key(name: str) -> None:
    """Settings › Connections › Remove. Models that need the key stay, marked as missing it."""
    from dotenv import dotenv_values, unset_key

    env = _env_name(name)
    path = cfgmod.env_path()
    if path.exists() and env in dotenv_values(path):
        unset_key(str(path), env, quote_mode="never")


def add_gemini_notes() -> None:
    """A Gemini key makes Gemini a notes model (owner's choice 2026-11-12), unless a Gemini model is already in
    the list. With no notes model yet, it becomes the one that writes the notes."""
    conf = cfgmod.load_config()

    def is_gemini(entry: str) -> bool:
        return entry.startswith("gemini:") or (entry.startswith("custom:") and conf.model_entry(entry).provider == "gemini")

    if any(is_gemini(c) for c in conf.llm.notes_choices):
        return
    update_settings({"llm": {"notes_choices": [*conf.llm.notes_choices, GEMINI_NOTES]}})
    if not conf.llm.tasks["notes"]:
        set_notes_model(GEMINI_NOTES)


def api_keys(conf) -> list[dict[str, Any]]:
    """Settings › Connections: every provider key that is set or used by a model, Groq and Gemini always.
    Only whether a key is set leaves this function, never the key."""
    keys = cfgmod.load_keys()
    used: dict[str, list[str]] = {}
    for m in conf.models:
        env = KEY_FIELDS["gemini"] if m.provider == "gemini" else m.key_name
        if env:
            used.setdefault(env, []).append(m.label or m.model)
    out = []
    for name, (env, label, url) in PROVIDER_KEYS.items():
        if name in ("groq", "gemini") or keys.get(env) or env in used:
            out.append({"name": name, "label": label, "url": url, "set": bool(keys.get(env)), "used_by": used.get(env, [])})
    for env, by in used.items():
        if env not in KEY_FIELDS.values():
            out.append({"name": env, "label": ", ".join(by), "url": None, "set": bool(keys.get(env)), "used_by": by})
    return out


# --- courses -----------------------------------------------------------------------------------------------


def _user_courses_path() -> Path:
    return cfgmod.config_dir() / "courses.yaml"


def save_course(course: dict[str, Any]) -> Course:
    """Add or update a course (by id). The id is made from the name when missing."""
    c = dict(course)
    if not c.get("id"):
        c["id"] = re.sub(r"[^a-z0-9]+", "-", c.get("name", "").lower()).strip("-")[:40] or "course"
    if not c.get("notes_language"):
        c["notes_language"] = c.get("language", "nl")
    c["extra_terms"] = [t.strip() for t in c.get("extra_terms", []) if t and t.strip()]
    c["lecturer"] = (c.get("lecturer") or "").strip() or None
    c["corrections"] = {" ".join(k.split()): " ".join(v.split()) for k, v in (c.get("corrections") or {}).items()
                        if k.strip() and v.strip() and k.strip().lower() != v.strip().lower()}
    model = Course.model_validate(c)
    path = _user_courses_path()
    data = _read(path) if path.exists() else _read(cfgmod.courses_file() or path)
    courses = [x for x in data.get("courses", []) if x.get("id") != model.id]
    courses.append(model.model_dump(exclude_none=True))
    _write_validated(path, {"courses": courses}, cfgmod.load_courses)
    return model


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def import_courses(found: list[dict]) -> dict[str, int]:
    """Sequo's courses: an existing course (same code or name) gets the codes, an unknown one is added.

    Nothing else about an existing course changes, and nothing is removed.
    """
    linked = added = 0
    for entry in found:
        codes = entry.get("codes") or []
        wanted = {c.upper() for c in codes}
        courses = cfgmod.load_courses()
        same = next((c for c in courses if wanted & {x.upper() for x in c.codes}), None) \
            or next((c for c in courses if _name_key(c.name) == _name_key(entry.get("name", ""))), None)
        if same:
            missing = [c for c in codes if c.upper() not in {x.upper() for x in same.codes}]
            if missing:
                save_course({**same.model_dump(), "codes": [*same.codes, *missing]})
            linked += 1
        else:
            save_course({"name": entry["name"], "codes": codes, "language": entry.get("language") or "nl"})
            added += 1
    return {"linked": linked, "added": added}


def delete_course(course_id: str) -> None:
    path = _user_courses_path()
    data = _read(path) if path.exists() else _read(cfgmod.courses_file() or path)
    courses = [x for x in data.get("courses", []) if x.get("id") != course_id]
    if len(courses) == len(data.get("courses", [])):
        raise KeyError(course_id)
    _write_validated(path, {"courses": courses}, cfgmod.load_courses)


# --- folders (own folders on top of the automatic per-course grouping) ------------------------------------


def _folders_path() -> Path:
    return cfgmod.load_config().paths.jobs_dir / "folders.json"


def folders() -> dict[str, Any]:
    path = _folders_path()
    return read_json(path) if path.exists() else {"folders": [], "assign": {}}


def save_folders(data: dict[str, Any]) -> dict[str, Any]:
    names = [f["name"].strip() for f in data.get("folders", []) if f.get("name", "").strip()]
    clean = {"folders": [{"id": f["id"], "name": f["name"].strip()} for f in data.get("folders", [])
                         if f.get("id") and f.get("name", "").strip()][:100],
             "assign": {job: fid for job, fid in data.get("assign", {}).items()
                        if re.fullmatch(r"[\w.-]+", job) and any(f["id"] == fid for f in data.get("folders", []))}}
    if len(set(n.lower() for n in names)) != len(names):
        raise ValueError("two folders with the same name")
    write_json(_folders_path(), clean)
    return clean


# --- what is set up (cheap checks only: no paid calls) ----------------------------------------------------


_login_cache: tuple[float, dict[str, Any]] | None = None


def claude_login() -> dict[str, Any]:
    """Cached for a minute: the dashboard asks every few seconds and `claude auth status` takes ~1 s."""
    global _login_cache
    if _login_cache and time.monotonic() - _login_cache[0] < 60:
        return _login_cache[1]
    result = _claude_login()
    _login_cache = (time.monotonic(), result)
    return result


def _claude_login() -> dict[str, Any]:
    exe = find_claude()
    if not exe:
        return {"installed": False, "logged_in": False}
    try:
        out = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        data = json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"installed": True, "logged_in": None}
    # only these two fields leave this function (the status also holds e-mail and organisation)
    return {"installed": True, "logged_in": bool(data.get("loggedIn")), "plan": data.get("subscriptionType")}


def local_whisper_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("faster_whisper") is not None and shutil.which("nvidia-smi") is not None
    except Exception:  # noqa: BLE001
        return False


# --- welcome steps (simple mode) ---------------------------------------------------------------------------

KEY_TESTS = {
    "groq": ("https://api.groq.com/openai/v1/models", lambda key: {"Authorization": f"Bearer {key}"}),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models", lambda key: {"x-goog-api-key": key}),
}


def test_key(name: str, value: str, client: Any = None) -> dict[str, Any]:
    """Does the service accept this key? Lists the models (free, uses no quota). Saves the key when it works.

    reason: ok · format (doesn't look like a key) · rejected · location (Gemini not offered here) · offline · error
    """
    import httpx

    if name not in KEY_TESTS:
        raise ValueError(f"no test for {name!r}")
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-.]{10,200}", value):
        return {"ok": False, "reason": "format"}
    url, headers = KEY_TESTS[name]
    try:
        r = (client or httpx).get(url, headers=headers(value), timeout=20)
    except httpx.HTTPError:
        return {"ok": False, "reason": "offline"}
    if r.status_code == 200:
        set_key(name, value)
        return {"ok": True, "reason": "ok"}
    text = r.text.lower()
    if "location is not supported" in text or "user location" in text:
        return {"ok": False, "reason": "location"}
    if r.status_code in (400, 401, 403):
        return {"ok": False, "reason": "rejected"}
    return {"ok": False, "reason": "error", "detail": f"HTTP {r.status_code}"}


def finish_welcome() -> None:
    update_settings({"app": {"welcomed": True}})


WHISPER_CHOICES = {"accurate": "large-v3-turbo", "fast": "small"}  # measured on a CPU, CHANGELOG 2026-11-11


def setup_simple(folder: Path, whisper: str = "accurate") -> None:
    """Simple mode for a new user (the Windows installer runs `lecture setup-simple`): no Mac, hub or LaTeX;
    Groq first with local Whisper as fallback; lectures in `folder`. Written to settings.yaml, so a second run
    (an update) only changes these keys and keeps the keys, courses and welcome state."""
    if whisper not in WHISPER_CHOICES:
        raise ValueError(f"whisper must be one of {', '.join(WHISPER_CHOICES)}")
    folder = folder.expanduser().resolve()
    if "llm" not in _read(cfgmod.settings_path()):
        # First run: no notes models (Claude needs Claude Code; owner's choice 2026-11-12). A Gemini key adds
        # Gemini (add_gemini_notes); an update keeps whatever the user chose since.
        start = [GEMINI_NOTES] if key_status()["gemini"] else []
        update_settings({"llm": {"notes_choices": start, "tasks": {"notes": start}}})
    update_settings({
        "app": {"simple": True},
        "paths": {"jobs_dir": str(folder / "jobs"), "inbox_dir": str(folder / "inbox")},
        "stt": {"providers": ["groq", "local"],
                "local": {"skip_on_battery": False, "device": "auto", "model": WHISPER_CHOICES[whisper]}},
        "termfix": {"enabled": False},
    })
