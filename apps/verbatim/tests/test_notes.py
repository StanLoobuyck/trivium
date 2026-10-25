"""Stage 7 notes: claude -p output contract, schedule, validation, provider chain, outputs (offline)."""

import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from lecture.config import Course, load_config
from lecture.providers import claude_cli
from lecture.providers.llm import LLMBadOutput, LLMLimit, LLMResult, LLMUnavailable
from lecture.report import NullReporter
from lecture.stages import s7_notes

FIX = Path(__file__).parent / "fixtures" / "claude_cli"
COURSE = Course(id="dep", name="Digitale elektronica", language="nl", notes_language="nl")


@pytest.fixture
def conf(xdg):
    """All optional extras on: most tests here check exam hints, quiz and flashcards."""
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text("notes:\n  outputs: {exam_hints: true, quiz: true, flashcards: true, glossary: true}\n")
    return load_config()


def test_default_is_notes_and_transcript_only(xdg):
    conf = load_config()  # repo defaults: no extras
    assert s7_notes.enabled_extras(conf) == set()
    schema = s7_notes.notes_schema(s7_notes.enabled_extras(conf))
    assert set(schema["properties"]) == {"sections", "summary"}
    assert "exam_hints" not in schema["properties"]["sections"]["items"]["properties"]
    assert "`quiz`" not in s7_notes.system_prompt(COURSE, 1, set())
    inputs = _inputs(conf)
    assert all(not s.exam_candidates for s in inputs)  # no regex hints asked for
    notes = s7_notes.LectureNotes.model_validate({"sections": [
        {k: v for k, v in sec.items() if k != "exam_hints"} for sec in _answer()["sections"]], "summary": "S."})
    _, check = s7_notes.validate(notes.model_dump(), inputs, 30)
    assert not check.fatal
    assert set(s7_notes.render_outputs(notes, inputs, "Les 1", "nl", "t", set())) == {"notes.md", "summary.md"}


# --- claude -p output (real outputs of Claude Code 2.1.302) ------------------------------------------------


def _parse(name, rc=0):
    return claude_cli.parse_output((FIX / name).read_text(), "", rc, 1.0, "sonnet")


def test_claude_structured_output_and_usage():
    r = _parse("structured_answer.json")
    assert r.data["bullets"][0]["ts"] == "0:01:05"
    assert r.model == "claude-sonnet-5-5" and r.input_tokens > 1000 and r.output_tokens > 0


def test_claude_text_answer_without_schema_is_bad_output():
    with pytest.raises(LLMBadOutput):
        _parse("text_answer.json")  # result "Brussel": no structured_output, not JSON


def test_claude_not_logged_in_is_unavailable_not_failure():
    released = []
    with pytest.raises(LLMUnavailable, match="not logged in"):
        claude_cli.parse_output((FIX / "not_logged_in.json").read_text(), "", 1, 0.1, "sonnet",
                                on_not_counted=lambda: released.append(1))
    assert released == [1]  # a call that never ran doesn't count against the daily cap


def test_claude_usage_limit_is_a_limit():
    out = json.loads((FIX / "not_logged_in.json").read_text())
    out["result"] = "Claude AI usage limit reached|1792300000"
    with pytest.raises(LLMLimit):
        claude_cli.parse_output(json.dumps(out), "", 1, 0.1, "sonnet")


def test_claude_command_has_no_tools_no_user_settings():
    cli = object.__new__(claude_cli.ClaudeCLI)
    cli.exe, cli.model = "claude", "claude-sonnet-5-5"
    cmd = cli.command("sys", {"type": "object"})
    assert cmd[cmd.index("--tools") + 1] == "" and cmd[cmd.index("--setting-sources") + 1] == "project"
    assert "--no-session-persistence" in cmd and "--strict-mcp-config" in cmd


@pytest.mark.parametrize("schedule,now,allowed,next_start", [
    ("always", "12:00", True, None),
    ("22:00-08:00", "23:30", True, None),
    ("22:00-08:00", "07:59", True, None),
    ("22:00-08:00", "12:00", False, "22:00"),
    ("12:00-13:00, 22:00-08:00", "13:30", False, "22:00"),
])
def test_schedule_windows(schedule, now, allowed, next_start):
    t = datetime(2026, 10, 17, *map(int, now.split(":")))
    ok, nxt = claude_cli.schedule_allows(schedule, t)
    assert ok == allowed and (nxt is None if next_start is None else f"{nxt:%H:%M}" == next_start)


# --- input, validation, chain ------------------------------------------------------------------------------


def _inputs(conf):
    segments = [{"start": 10.0 * i, "end": 10.0 * i + 9, "text": t} for i, t in enumerate([
        "Een NAND-poort is een AND met een inverter.", "Dat moet je kennen voor het examen.",
        "Nu de multiplexer.", "De selectiebit kiest de ingang.", "Let op met de volgorde."])]
    sections = [{"index": 1, "title": "NAND", "start": 0.0, "end": 20.0, "slides": [{"file": "a.pdf", "page": 3}]},
                {"index": 2, "title": "MUX", "start": 20.0, "end": 49.0, "slides": []}]
    slides = [{"file": "a.pdf", "page": 3, "title": "NAND", "text": "NAND = NOT AND", "notes": ""}]
    return s7_notes.build_inputs(sections, segments, slides, "nl", conf)


def _answer(hints=True, ts1="0:00:00"):
    sec = lambda i, title, ts, hint: {"index": i, "title": title, "slide_summary": "", "lecturer_additions":
                                      [{"text": "uitleg", "ts": ts}], "definitions": [], "examples": [],
                                      "exam_hints": [hint] if hints and hint else []}
    return {"sections": [sec(1, "NAND", ts1, {"quote": "Dat moet je kennen", "ts": "0:00:10"}),
                         sec(2, "MUX", "0:00:30", {"quote": "Let op", "ts": "0:00:40"})],
            "summary": "Samenvatting.", "glossary": [{"term": "NAND", "definition": "NOT AND", "ts": "0:00:00"}],
            "quiz": [{"q": "Wat is NAND?", "a": "NOT AND", "ts": "0:00:00", "type": "open", "options": []}],
            "flashcards": [{"front": "NAND; poort", "back": "NOT \"AND\"", "ts": "0:00:00"}]}


def test_inputs_carry_slide_text_and_regex_exam_hints(conf):
    inputs = _inputs(conf)
    assert inputs[0].pages == [3] and "NAND = NOT AND" in inputs[0].slide_text
    assert [t for t, _ in inputs[0].exam_candidates] == [10.0]
    assert [t for t, _ in inputs[1].exam_candidates] == [40.0]  # "let op"
    text = inputs[0].render()
    assert "[00:00:10] Dat moet je kennen" in text and "Exam-hint candidates" in text


def test_validation_drops_bad_timestamps_and_requires_exam_hints(conf):
    inputs = _inputs(conf)
    notes, check = s7_notes.validate(_answer(), inputs, 30)
    assert not check.fatal and not check.dropped
    notes, check = s7_notes.validate(_answer(ts1="1:00:00"), inputs, 30)  # one bullet an hour off
    assert len(check.dropped) == 1 and notes.sections[0].lecturer_additions == []
    _, check = s7_notes.validate(_answer(hints=False), inputs, 30)
    assert len(check.missing_hints) == 2 and check.fatal
    bad = _answer()
    bad["sections"] = bad["sections"][:1]
    _, check = s7_notes.validate(bad, inputs, 30)
    assert any("sections must be exactly [1, 2]" in p for p in check.fatal)


class FakeLLM:
    def __init__(self, name, answers):
        self.name, self.answers, self.messages = name, list(answers), []

    def generate(self, system, user, schema):
        self.messages.append(user)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return LLMResult(data=a, model=f"{self.name}-model", input_tokens=100, output_tokens=50, elapsed_s=1.0)


def test_chain_retries_with_problems_then_falls_back(conf, tmp_path):
    claude = FakeLLM("claude", [_answer(hints=False), _answer(hints=False)])  # keeps dropping hints
    gemini = FakeLLM("gemini", [_answer()])
    # hints-only problems on the 2nd attempt are fixed in code rather than thrown away
    notes, records = s7_notes.make_notes(tmp_path, _inputs(conf), "Les 1", COURSE, conf,
                                         [("claude:x", lambda: claude), ("gemini:y", lambda: gemini)], NullReporter())
    assert "previous answer was rejected" in claude.messages[1] and "[00:00:10]" in claude.messages[1]
    assert records[0]["provider"] == "claude:x" and records[0]["flags"]
    assert [h.quote for h in notes.sections[0].exam_hints] == ["Dat moet je kennen voor het examen."]
    assert gemini.messages == []

    # rerun: the saved batch is reused, no calls
    again = FakeLLM("claude", [])
    s7_notes.make_notes(tmp_path, _inputs(conf), "Les 1", COURSE, conf, [("claude:x", lambda: again)], NullReporter())
    assert again.messages == []


def test_chain_moves_on_after_schema_failures_and_limits(conf, tmp_path):
    broken = FakeLLM("claude", [{"nonsense": 1}, {"nonsense": 2}])
    gemini = FakeLLM("gemini", [_answer()])
    _, records = s7_notes.make_notes(tmp_path, _inputs(conf), "Les 1", COURSE, conf,
                                     [("claude:x", lambda: broken), ("gemini:y", lambda: gemini)], NullReporter())
    assert records[0]["provider"] == "gemini:y" and len(broken.messages) == 2


def test_all_providers_limited_means_pending_not_failed(conf, tmp_path):
    later = datetime(2026, 10, 17, 22, 0)
    limited = FakeLLM("claude", [LLMLimit("schedule", later)])

    def no_key():
        raise LLMUnavailable("no key")

    with pytest.raises(s7_notes.NotesPending) as exc:
        s7_notes.make_notes(tmp_path, _inputs(conf), "Les 1", COURSE, conf,
                            [("claude:x", lambda: limited), ("gemini:y", no_key)], NullReporter())
    assert exc.value.resume_at == later and len(exc.value.reasons) == 2
    assert not list(tmp_path.glob("batch_*.json"))


def test_batches_split_by_size_and_merge(conf):
    inputs = _inputs(conf)
    assert len(s7_notes.make_batches(inputs, 10**6)) == 1
    assert [len(b) for b in s7_notes.make_batches(inputs, 1)] == [1, 1]
    a = s7_notes.LectureNotes.model_validate(_answer())
    merged = s7_notes.merge([a, a])
    assert len(merged.sections) == 4 and len(merged.glossary) == 1 and merged.summary.count("Samenvatting") == 2


def test_outputs_and_anki_csv(conf):
    notes = s7_notes.LectureNotes.model_validate(_answer())
    out = s7_notes.render_outputs(notes, _inputs(conf), "Les 1", "nl", "dep les-1")
    assert "## 1. NAND (slide 3) · 00:00:00–00:00:20" in out["notes.md"]
    assert "**Examentips**" in out["notes.md"] and "[00:00:10]" in out["exam_hints.md"]
    lines = out["flashcards_anki.csv"].splitlines()
    assert lines[:3] == ["#separator:Semicolon", "#html:false", "#tags column:3"]
    row = next(csv.reader(io.StringIO(lines[3]), delimiter=";"))
    assert row == ["NAND; poort", 'NOT "AND" [00:00:00]', "dep les-1"]  # separators inside fields are quoted


def test_study_pack_contains_instructions_and_every_section(conf):
    pack = s7_notes.study_pack(_inputs(conf), "Les 1", COURSE, conf)
    assert "Use only the transcript and the slides" in pack
    assert "## Section 1" in pack and "## Section 2" in pack and "{notes_language}" not in pack
