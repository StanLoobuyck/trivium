"""LaTeX course notes: runs the latex-notes skill (skill/latex-notes) on a finished lecture with Claude Code.

The steps that need no judgement happen here, so they cost no Claude quota: preparing the material and setting up
the course folder. The skill is sent as the prompt instead of being discovered: `--setting-sources project` keeps the
user's own CLAUDE.md and memory out of the run, as for the notes (providers/claude_cli.py).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

from . import config as cfgmod
from .config import Config
from .hub import trailing_number
from .inbox import lecture_number
from .providers.claude_cli import _LIMIT, _LOGIN, ClaudeCLI
from .providers.llm import LLMLimit, LLMUnavailable
from .report import Reporter
from .util import find_claude, read_json, slugify

SKILL_DIR = Path(__file__).resolve().parents[2] / "skill" / "latex-notes"
MODEL = "claude-sonnet-5-5"
TIMEOUT_S = 3600.0
TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(uv run *)", "Bash(cd *)", "Bash(tectonic *)", "Bash(cp *)",
         "Bash(mkdir *)", "Bash(ls *)", "Bash(command -v *)"]
BEGIN, END = "% LESSEN BEGIN", "% LESSEN END"


class LatexFailed(Exception):
    pass


def course_folder(conf: Config, course_id: str) -> Path:
    course = next((c for c in cfgmod.load_courses() if c.id == course_id), None)
    name = (course.name if course else course_id).replace("/", "-")
    return conf.paths.latex_dir / name


def lecture_file(manifest: dict) -> str:
    return f"{manifest.get('date')}_{slugify(manifest.get('title') or 'les')}"


def lecture_nr(manifest: dict) -> int | None:
    title = manifest.get("title") or ""
    media = Path(manifest.get("input", {}).get("media", "")).stem
    return lecture_number(title) or lecture_number(media) or trailing_number(title) or trailing_number(media)


def academic_year(date: str) -> str:
    year, month = int(date[:4]), int(date[5:7])
    start = year if month >= 9 else year - 1
    return f"{start}–{start + 1}"


def add_input(main_tex: Path, name: str) -> None:
    """The lecture's \\input between the markers, sorted by date (the file names start with it)."""
    text = main_tex.read_text(encoding="utf-8")
    head, rest = text.split(BEGIN, 1)
    body, tail = rest.split(END, 1)
    lines = {line.strip() for line in body.splitlines() if line.strip()} | {f"\\input{{lessen/{name}}}"}
    main_tex.write_text(f"{head}{BEGIN}\n" + "\n".join(sorted(lines)) + f"\n{END}{tail}", encoding="utf-8")


def setup_course(folder: Path, course: str, manifest: dict, lecturer: str | None) -> Path:
    """Step 2 of the skill. Never touches an existing main.tex except for this lecture's \\input line."""
    (folder / "lessen").mkdir(parents=True, exist_ok=True)
    (folder / "slides").mkdir(exist_ok=True)
    (folder / "figures").mkdir(exist_ok=True)
    if not (folder / "lesnotities.sty").exists():
        shutil.copy(SKILL_DIR / "templates" / "lesnotities.sty", folder)
    main_tex = folder / "main.tex"
    english = manifest.get("language") == "en"
    if not main_tex.exists():
        text = (SKILL_DIR / "templates" / "main.tex").read_text(encoding="utf-8")
        for key, value in (("%%COURSE%%", course), ("%%SUBTITLE%%", "Lecture notes" if english else "Lesnotities"),
                           ("%%AUTHOR%%", lecturer or ""), ("%%YEAR%%", academic_year(manifest["date"])),
                           ("%%LANG%%", "en" if english else "nl")):
            text = text.replace(key, value)
        main_tex.write_text(text, encoding="utf-8")
    name = lecture_file(manifest)
    tex = folder / "lessen" / f"{name}.tex"
    if not tex.exists():
        tex.write_text("% Verbatim: being written\n", encoding="utf-8")  # main.tex must keep compiling
    add_input(main_tex, name)
    return tex


def prompt(job_root: Path, work: Path, folder: Path, tex: Path, manifest: dict) -> str:
    body = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2]
    number = lecture_nr(manifest)
    given = (f"Started from Verbatim. Lecture: {manifest.get('title')} ({manifest.get('date')}), "
             f"lecture number: {number if number else 'none: use the title'}. Job folder: {job_root}. "
             f"Work folder, already prepared: {work}. Course folder, already set up: {folder}. "
             f"Lecture file to write: {tex.relative_to(folder)}.")
    return body.replace("$ARGUMENTS", given).replace("~/.claude/skills/latex-notes", str(SKILL_DIR))


def command(exe: str, job_root: Path, folder: Path) -> list[str]:
    return [exe, "-p", "--output-format", "stream-json", "--verbose", "--model", MODEL, "--effort", "high",
            "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config",
            "--allowedTools", ",".join(TOOLS), "--add-dir", str(job_root), str(SKILL_DIR)]


def stage_of(tool: str, tool_input: dict) -> str | None:
    """What a tool call means for the user; None keeps the current stage."""
    command_line = str(tool_input.get("command", ""))
    if "tectonic" in command_line:
        return "latex_compile"
    if "crop.py" in command_line:
        return "latex_figures"
    if tool in ("Write", "Edit") and "/lessen/" in str(tool_input.get("file_path", "")):
        return "latex_write"
    return "latex_read" if tool == "Read" else None


def follow(lines, rep: Reporter) -> dict[str, Any]:
    """Reads Claude's stream-json output: shows the stage, returns the final result."""
    result: dict[str, Any] = {}
    stage = None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            result = event
        for block in (event.get("message") or {}).get("content") or [] if event.get("type") == "assistant" else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = stage_of(block.get("name", ""), block.get("input") or {})
                if name and name != stage:
                    rep.stage(stage := name)
    return result


def check_result(result: dict[str, Any], returncode: int, stderr: str) -> None:
    message = str(result.get("result") or stderr or "")[:300]
    if result and not result.get("is_error") and returncode == 0:
        return
    if _LOGIN.search(message):
        raise LLMUnavailable(f"Claude Code is not logged in ({message}) — run `claude` once and /login")
    if result.get("api_error_status") == 429 or _LIMIT.search(message):
        raise LLMLimit(f"Claude usage limit: {message[:200]}")
    raise LatexFailed(f"claude -p exit {returncode}: {message or 'no result'}")


def prepare(job_root: Path, work: Path) -> None:
    uv = shutil.which("uv")
    if not uv:
        raise LatexFailed("uv not found")
    done = subprocess.run([uv, "run", str(SKILL_DIR / "scripts" / "prepare.py"), "--job", str(job_root),
                           "--out", str(work)], capture_output=True, text=True)
    if done.returncode:
        raise LatexFailed(f"prepare.py: {done.stderr.strip()[-300:]}")


def run(job_root: Path, conf: Config, rep: Reporter) -> Path:
    """Writes the lecture's notes and compiles the course document. Returns the PDF."""
    exe = find_claude()
    if not exe:
        raise LLMUnavailable("Claude Code (`claude`) not found on PATH")
    ClaudeCLI(conf, MODEL)._check_budget()  # shares the daily cap and schedule with the notes
    rep.stage("latex_prepare")
    manifest = read_json(job_root / "manifest.json")
    folder = course_folder(conf, manifest["course"])
    tex_name = lecture_file(manifest)
    work = folder / ".work" / tex_name
    prepare(job_root, work)
    lecturer = read_json(work / "lecture.json").get("lecturer")
    tex = setup_course(folder, folder.name, manifest, lecturer)
    pdf = folder / "main.pdf"
    before = pdf.stat().st_mtime if pdf.exists() else 0.0

    proc = subprocess.Popen(command(exe, job_root, folder), cwd=folder, text=True, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timer = threading.Timer(TIMEOUT_S, proc.kill)
    timer.start()
    try:
        errors: list[str] = []
        reader = threading.Thread(target=lambda: errors.extend(proc.stderr), daemon=True)  # a full pipe would block
        reader.start()
        proc.stdin.write(prompt(job_root, work, folder, tex, manifest))
        proc.stdin.close()
        result = follow(proc.stdout, rep)
        proc.wait()
        reader.join(5)
    finally:
        timer.cancel()
    check_result(result, proc.returncode, "".join(errors))
    if tex.read_text(encoding="utf-8").startswith("% Verbatim: being written"):
        raise LatexFailed("Claude finished without writing the lecture file")
    if not pdf.exists() or pdf.stat().st_mtime <= before:
        raise LatexFailed("the .tex is written, but the PDF wasn't made: see main.tex in the course folder")
    return pdf
