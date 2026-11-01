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
KEY_FIELDS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "mac": "LECTURE_MAC_TOKEN"}


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


def set_outputs(outputs: dict[str, bool]) -> None:
    allowed = {"exam_hints", "quiz", "flashcards", "glossary"}
    if set(outputs) - allowed:
        raise ValueError(f"unknown outputs: {', '.join(set(outputs) - allowed)}")
    update_settings({"notes": {"outputs": {k: bool(v) for k, v in outputs.items()}}})


# --- API keys ----------------------------------------------------------------------------------------------


def key_status() -> dict[str, bool]:
    keys = cfgmod.load_keys()
    return {name: bool(keys[env]) for name, env in KEY_FIELDS.items()}


def set_key(name: str, value: str) -> None:
    from dotenv import set_key as dotenv_set

    if name not in KEY_FIELDS:
        raise ValueError(f"unknown key {name!r}")
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-.]{10,200}", value):
        raise ValueError("that doesn't look like an API key")
    path = cfgmod.env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    dotenv_set(str(path), KEY_FIELDS[name], value, quote_mode="never")
    path.chmod(0o600)


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
    data = _read(path) if path.exists() else _read(cfgmod.courses_file())
    courses = [x for x in data.get("courses", []) if x.get("id") != model.id]
    courses.append(model.model_dump(exclude_none=True))
    _write_validated(path, {"courses": courses}, cfgmod.load_courses)
    return model


def delete_course(course_id: str) -> None:
    path = _user_courses_path()
    data = _read(path) if path.exists() else _read(cfgmod.courses_file())
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
        out = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=15)
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
