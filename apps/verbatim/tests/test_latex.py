"""LaTeX notes (latex.py): course folder, Claude's output, and the queue. No Claude: its output is canned."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lecture import latex
from lecture import queue as q
from lecture.providers.llm import LLMLimit, LLMUnavailable
from lecture.report import NullReporter

MANIFEST = {"title": "Les 3", "date": "2026-10-07", "course": "x", "language": "nl",
            "input": {"media": "/v/RZL 3.mp4"}}


def test_names_and_year():
    assert latex.lecture_file(MANIFEST) == "2026-10-07_les-3"
    assert latex.lecture_nr({"title": "Vak - Ingenieurswetenschappen 5 - 2026 (2026-10-19)", "input": {}}) == 5
    assert latex.academic_year("2026-10-07") == "2026–2027" and latex.academic_year("2027-02-10") == "2026–2027"


def test_setup_course_and_sorted_inputs(tmp_path):
    folder = tmp_path / "Vak"
    tex = latex.setup_course(folder, "Vak", MANIFEST, "Prof")
    assert tex == folder / "lessen" / "2026-10-07_les-3.tex" and tex.exists()
    latex.setup_course(folder, "Vak", {**MANIFEST, "title": "Les 1", "date": "2026-09-23"}, None)
    latex.setup_course(folder, "Vak", MANIFEST, None)    # again: no double line
    main = (folder / "main.tex").read_text(encoding="utf-8")
    assert "\\textbf{Vak}" in main and "{Prof}" in main and "%%" not in main.replace("%% ", "")
    assert main.count("\\input{lessen/") == 2
    assert main.index("2026-09-23_les-1") < main.index("2026-10-07_les-3")
    assert (folder / "lesnotities.sty").exists()


def test_existing_lecture_file_is_kept(tmp_path):
    tex = latex.setup_course(tmp_path / "Vak", "Vak", MANIFEST, None)
    tex.write_text("eigen tekst")
    latex.setup_course(tmp_path / "Vak", "Vak", MANIFEST, None)
    assert tex.read_text() == "eigen tekst"


def test_prompt_is_for_a_run_without_questions(tmp_path):
    tex = latex.setup_course(tmp_path / "Vak", "Vak", MANIFEST, None)
    text = latex.prompt(Path("/jobs/j"), tmp_path / "w", tmp_path / "Vak", tex, MANIFEST)
    assert "Started from Verbatim" in text and "lecture number: 3" in text and "lessen/2026-10-07_les-3.tex" in text
    assert "$ARGUMENTS" not in text and "~/.claude/skills" not in text and str(latex.SKILL_DIR) in text
    assert not text.lstrip().startswith("name:")
    assert "<skill>" not in text and "main.pdf had 0 pages" in text
    assert "Density" in text and "3 pages per hour" in text and "next to the slides" in text
    assert "being redone" in latex.prompt(Path("/jobs/j"), tmp_path / "w", tmp_path / "Vak", tex, MANIFEST, None)


def test_command_keeps_the_users_own_settings_out():
    cmd = latex.command("claude", Path("/jobs/j"), Path("/c"))
    assert cmd[cmd.index("--setting-sources") + 1] == "project" and cmd[cmd.index("--model") + 1] == latex.MODEL
    assert "--dangerously-skip-permissions" not in cmd and "Write" in cmd[cmd.index("--allowedTools") + 1]


def tool(name, **tool_input):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": name, "input": tool_input}]}})


def test_follow_shows_stages_and_returns_the_result():
    seen = []

    class Rep(NullReporter):
        def stage(self, name):
            seen.append(name)

    lines = ["not json", tool("Read", file_path="/w/parts.md"), tool("Read", file_path="/w/lecture.json"),
             tool("Write", file_path="/c/lessen/a.tex"), tool("Bash", command="uv run crop.py a.pdf 1"),
             tool("Bash", command="cd /c && tectonic main.tex"), json.dumps({"type": "result", "result": "ok"})]
    assert latex.follow(lines, Rep())["result"] == "ok"
    assert seen == ["latex_read", "latex_write", "latex_figures", "latex_compile"]


def test_check_result():
    latex.check_result({"result": "ok"}, 0, "")
    with pytest.raises(LLMLimit):
        latex.check_result({"is_error": True, "result": "usage limit reached"}, 1, "")
    with pytest.raises(LLMUnavailable):
        latex.check_result({"is_error": True, "result": "Not logged in"}, 1, "")
    with pytest.raises(latex.LatexFailed):
        latex.check_result({}, 1, "kapot")


def test_queue_runs_retries_and_recovers(tmp_path, monkeypatch):
    queue = q.Queue(tmp_path / "queue.json")
    item = queue.add_latex(tmp_path / "job", "/v.mp4", "x")
    assert queue.add_latex(tmp_path / "job", "/v.mp4", "x")["id"] == item["id"]  # no double click
    assert queue.claim_latex(1)["status"] == "latex"
    assert queue.recover(lambda pid: False) == [item["id"]]
    claimed = queue.claim_latex(1)

    def broken(*a):
        raise latex.LatexFailed("kapot")

    monkeypatch.setattr(q, "notify", lambda *a, **k: None)
    monkeypatch.setattr(latex, "run", broken)
    q.latex_item(queue, claimed, None)
    state = queue.snapshot()["items"][0]
    assert state["status"] == "failed" and state["failed_at"] == "latex" and "kapot" in state["error"]
    queue.retry(item["id"])
    assert queue.snapshot()["items"][0]["status"] == "latex_queued"

    def limited(*a):
        raise LLMLimit("usage limit")

    monkeypatch.setattr(latex, "run", limited)
    q.latex_item(queue, queue.claim_latex(1), None)
    state = queue.snapshot()["items"][0]
    assert state["status"] == "latex_queued" and state["resume_at"]


def load_check():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check", latex.SKILL_DIR / "scripts" / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PARTS = """## Part 1: A  [0:00–2:00] · slides p10
[0:00] tekst
## Part 2: B  [2:00–4:00] · slides p20 (slide match uncertain)
[3:59] tekst
"""


def test_check_finds_bad_moments_and_own_macros():
    check = load_check().check
    good = "\\les{1}{x}{y}\n\\slide{10}{0:30}\n\\slide{99}{}\n\\slide{21}{3:00}\n% CHECK: x\n"
    assert check(good, PARTS, None) == []
    found = check("\\les{1}{x}{y}\n\\slide{20}{1:00}\n\\slide{10}{0:30}\n\\slide{10}{9:00}\n\\slide{10}{alleen slide}\n"
                  "\\newcommand{\\x}{y}\n", PARTS, None)
    assert len(found) == 5 and any("back in time" in p for p in found) and any("end of the recording" in p for p in found)
    assert any("own macros" in p for p in found) and any("parts.md has slides" in p for p in found)


def test_check_page_budget():
    check = load_check().check
    tex = "\\les{1}{x}{y}\n"
    assert check(tex, PARTS, 2) == []          # a short recording still gets 2 pages
    assert "over the budget" in check(tex, PARTS, 3)[0]


def test_check_wants_notes_next_to_the_slides():
    check = load_check().check
    short = "\\begin{verbatim}\na\nb\nc\nd\n\\end{verbatim}\n"
    good = "\\les{1}{x}{y}\n\\onderwerp{A}\n\\kernpunt{k}\n" + short
    assert check(good, PARTS, None) == []
    copied = good.replace("d\n", "d\ne\n") + "\\onderwerp{B}\n\\slidefig{.5}{3}{0 0 0 0}{s.pdf}{c}\n"
    found = check(copied, PARTS, None)
    assert len(found) == 3 and "code block of 5 lines" in found[0]
    assert any("figure from the slides" in p for p in found) and any("without \\kernpunt: B" in p for p in found)
    assert check(copied, PARTS, None, without_slides=True) == ["topic without \\kernpunt: B"]
    assert check("\\les{1}{x}{y}\n", PARTS, 3, without_slides=True) == []


def test_prompt_names_the_mode(tmp_path):
    tex = latex.setup_course(tmp_path / "Vak", "Vak", MANIFEST, None)
    assert "Mode: next to the slides." in latex.prompt(Path("/jobs/j"), tmp_path / "w", tmp_path / "Vak", tex, MANIFEST)
    alone = latex.prompt(Path("/jobs/j"), tmp_path / "w", tmp_path / "Vak", tex, MANIFEST, 0, True)
    assert "Mode: without slides." in alone and "--without-slides" in alone
