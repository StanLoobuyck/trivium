"""Stage 7: study notes per slide section via an LLM, validated in code; plus the free study pack.

The LLM gets, per section: time range, slide text (+ speaker notes), the transcript with [h:mm:ss] lines,
and exam-hint candidates found by a fixed regex. The answer must follow `LectureNotes` (JSON schema sent
to the provider). Code then checks it: one entry per section, every bullet's timestamp inside its section
(± tolerance), every regex exam hint kept. A failed check is retried once with the problems listed; then
the next provider in llm.tasks.notes is tried. Raw answers are saved per batch in notes/ and reused.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from ..config import REPO_DIR, Config, Course
from ..providers.llm import LLMBadOutput, LLMLimit, LLMProvider, LLMResult, LLMUnavailable, inline_refs
from ..report import Reporter
from ..util import fmt_ts, hash_data, parse_ts, read_json, write_json

TS_PATTERN = r"^\d{1,2}:\d{2}:\d{2}$"
LANGUAGE_NAMES = {"nl": "Dutch (Flemish university style)", "en": "English"}
SLIDE_ONLY = {"nl": "(alleen op de slide)", "en": "(slide only)"}
LECTURER_WORD = {"nl": "de docent", "en": "the lecturer"}


# --- the notes format (also the JSON schema sent to the LLM) -------------------------------------------


class Point(BaseModel):
    text: str
    ts: str = Field(pattern=TS_PATTERN)


class Definition(BaseModel):
    term: str
    definition: str
    ts: str = Field(pattern=TS_PATTERN)


class ExamHint(BaseModel):
    quote: str
    ts: str = Field(pattern=TS_PATTERN)


class SectionNotes(BaseModel):
    index: int
    title: str
    slide_summary: str
    lecturer_additions: list[Point]
    definitions: list[Definition]
    examples: list[Point]
    exam_hints: list[ExamHint] = Field(default_factory=list)


class QuizItem(BaseModel):
    q: str
    a: str
    ts: str = Field(pattern=TS_PATTERN)
    type: Literal["open", "multiple_choice", "calculation"]
    options: list[str]


class Flashcard(BaseModel):
    front: str
    back: str
    ts: str = Field(pattern=TS_PATTERN)


class LectureNotes(BaseModel):
    sections: list[SectionNotes]
    summary: str
    glossary: list[Definition] = Field(default_factory=list)
    quiz: list[QuizItem] = Field(default_factory=list)
    flashcards: list[Flashcard] = Field(default_factory=list)


EXTRAS = ("exam_hints", "quiz", "flashcards", "glossary")


def enabled_extras(conf: Config) -> set[str]:
    return {name for name in EXTRAS if getattr(conf.notes.outputs, name)}


def notes_schema(extras: set[str] | frozenset[str] = frozenset(EXTRAS)) -> dict:
    """JSON schema sent to the LLM; optional extras that are off are left out (no tokens spent on them)."""
    schema = inline_refs(LectureNotes.model_json_schema())
    for name in ("glossary", "quiz", "flashcards"):
        if name not in extras:
            del schema["properties"][name]
    section = schema["properties"]["sections"]["items"]
    if "exam_hints" not in extras:
        del section["properties"]["exam_hints"]
    for obj in (schema, section):  # every remaining property is required (structured output works best so)
        obj["required"] = list(obj["properties"])
    return schema


# --- input ------------------------------------------------------------------------------------------------


@dataclass
class SectionInput:
    index: int
    title: str | None
    start: float
    end: float
    pages: list[int]
    slide_text: str
    speaker_notes: str
    lines: list[tuple[float, str]]
    exam_candidates: list[tuple[float, str]] = field(default_factory=list)

    def render(self) -> str:
        where = f" · slide {self.pages[0]}" + (f"–{self.pages[-1]}" if len(self.pages) > 1 else "") if self.pages else ""
        out = [f"## Section {self.index} · {fmt_ts(self.start)}–{fmt_ts(self.end)}{where}"
               + (f": {self.title}" if self.title else "")]
        if self.slide_text.strip():
            out += ["### Slide text", self.slide_text.strip()]
        if self.speaker_notes.strip():
            out += ["### Speaker notes", self.speaker_notes.strip()]
        out += ["### Transcript"] + [f"[{fmt_ts(t)}] {text}" for t, text in self.lines]
        if self.exam_candidates:
            out += ["### Exam-hint candidates (must appear in exam_hints)"]
            out += [f"[{fmt_ts(t)}] {text}" for t, text in self.exam_candidates]
        return "\n".join(out)


def exam_candidates(lines: list[tuple[float, str]], patterns: list[str]) -> list[tuple[float, str]]:
    if not patterns:  # an empty alternation would match every line
        return []
    regex = re.compile("|".join(rf"\b(?:{p})\b" for p in patterns), re.I)
    return [(t, text) for t, text in lines if regex.search(text)]


def build_inputs(sections: list[dict], segments: list[dict], slides: list[dict], language: str,
                 conf: Config) -> list[SectionInput]:
    by_page = {(s["file"], s["page"]): s for s in slides}
    patterns = conf.notes.exam_hint_patterns.get(language, []) if conf.notes.outputs.exam_hints else []
    out = []
    for sec in sections:
        shown = [by_page[(p["file"], p["page"])] for p in sec["slides"] if (p["file"], p["page"]) in by_page]
        lines = [(s["start"], s["text"].strip()) for s in segments
                 if sec["start"] <= s["start"] < sec["end"] and s["text"].strip()]
        out.append(SectionInput(
            index=sec["index"], title=sec["title"], start=sec["start"], end=sec["end"],
            pages=[s["page"] for s in shown],
            slide_text="\n\n".join(f"{s['title'] or ''}\n{s['text']}".strip() for s in shown),
            speaker_notes="\n\n".join(s["notes"] for s in shown if s["notes"]),
            lines=lines, exam_candidates=exam_candidates(lines, patterns)))
    return out


def estimate_tokens(text: str) -> int:
    return int(len(text) / 3.5) + 1  # Dutch/English prose; only used to size batches


def make_batches(inputs: list[SectionInput], max_tokens: int) -> list[list[SectionInput]]:
    batches: list[list[SectionInput]] = [[]]
    used = 0
    for sec in inputs:
        n = estimate_tokens(sec.render())
        if batches[-1] and used + n > max_tokens:
            batches.append([])
            used = 0
        batches[-1].append(sec)
        used += n
    return [b for b in batches if b]


def _drop_rules(template: str, names: set[str]) -> str:
    """Remove the prompt's rule bullets ("- `quiz`: …" plus their indented continuation) for extras that are off."""
    out, skipping = [], False
    for line in template.splitlines(keepends=True):
        if line.startswith("- `"):
            skipping = any(line.startswith(f"- `{n}`") for n in names)
        elif not line.startswith("  "):
            skipping = False
        if not skipping:
            out.append(line)
    return "".join(out)


def system_prompt(course: Course, n_batches: int, extras: set[str] | frozenset[str] = frozenset(EXTRAS)) -> str:
    template = _drop_rules((REPO_DIR / "prompts" / "notes_system.md").read_text(encoding="utf-8"),
                           set(EXTRAS) - set(extras))
    batch_note = " (this is one part of a longer lecture: summarise this part)" if n_batches > 1 else ""
    return template.format(notes_language=LANGUAGE_NAMES[course.notes_language],
                           slide_only=SLIDE_ONLY[course.notes_language], batch_note=batch_note,
                           lecturer_word=LECTURER_WORD[course.notes_language])


def user_message(heading: str, course: Course, batch: list[SectionInput], part: tuple[int, int]) -> str:
    head = [f"# Lecture: {heading}", f"Course: {course.name}. Spoken language: {course.language}."]
    if part[1] > 1:
        head.append(f"Part {part[0]} of {part[1]} of the lecture (sections {batch[0].index}–{batch[-1].index}).")
    return "\n".join(head) + "\n\n" + "\n\n".join(s.render() for s in batch) + "\n"


# --- validation -------------------------------------------------------------------------------------------


@dataclass
class Check:
    fatal: list[str] = field(default_factory=list)      # retry / next provider
    dropped: list[str] = field(default_factory=list)    # bullets removed (bad timestamps), reported
    missing_hints: list[tuple[float, str]] = field(default_factory=list)


def validate(data: dict, batch: list[SectionInput], tolerance_s: float) -> tuple[LectureNotes | None, Check]:
    check = Check()
    try:
        notes = LectureNotes.model_validate(data)
    except ValidationError as exc:
        check.fatal.append(f"answer doesn't match the schema: {str(exc)[:500]}")
        return None, check
    if [s.index for s in notes.sections] != [s.index for s in batch]:
        check.fatal.append(f"sections must be exactly {[s.index for s in batch]} in order, "
                           f"got {[s.index for s in notes.sections]}")
        return notes, check
    total = 0
    for sec, inp in zip(notes.sections, batch):
        lo, hi = inp.start - tolerance_s, inp.end + tolerance_s
        for name in ("lecturer_additions", "definitions", "examples", "exam_hints"):
            kept = []
            for item in getattr(sec, name):
                total += 1
                t = parse_ts(item.ts)
                if lo <= t <= hi:
                    kept.append(item)
                else:
                    check.dropped.append(f"section {inp.index} {name} [{item.ts}] outside "
                                         f"{fmt_ts(inp.start)}–{fmt_ts(inp.end)}: {_text(item)[:80]}")
            setattr(sec, name, kept)
        for t, text in inp.exam_candidates:
            if not any(abs(parse_ts(h.ts) - t) <= tolerance_s for h in sec.exam_hints):
                check.missing_hints.append((t, text))
    if total and len(check.dropped) > 0.15 * total:
        check.fatal.append(f"{len(check.dropped)} of {total} timestamps lie outside their section: copy "
                           "timestamps from the transcript lines of that section")
    if check.missing_hints:
        check.fatal.append("exam-hint candidates missing from exam_hints: "
                           + "; ".join(f"[{fmt_ts(t)}] {x[:60]}" for t, x in check.missing_hints))
    return notes, check


def _text(item) -> str:
    return getattr(item, "text", None) or getattr(item, "quote", None) or getattr(item, "term", "")


def add_missing_hints(notes: LectureNotes, batch: list[SectionInput], missing: list[tuple[float, str]]) -> None:
    """Last resort: put regex exam hints the LLM kept dropping in verbatim (flagged in review.md)."""
    for t, text in missing:
        sec = next(s for s, inp in zip(notes.sections, batch) if inp.start <= t < inp.end or inp is batch[-1])
        sec.exam_hints.append(ExamHint(quote=text, ts=fmt_ts(t)))
        sec.exam_hints.sort(key=lambda h: parse_ts(h.ts))


# --- running the chain ------------------------------------------------------------------------------------


class NotesPending(Exception):
    """No provider can make the notes now (limits, schedule, login); the job waits."""

    def __init__(self, reasons: list[str], resume_at: datetime | None):
        super().__init__("; ".join(reasons))
        self.reasons = reasons
        self.resume_at = resume_at


@dataclass
class BatchOutcome:
    notes: LectureNotes
    record: dict


def run_batch(providers: list[tuple[str, callable]], system: str, user: str, batch: list[SectionInput],
              conf: Config, rep: Reporter) -> BatchOutcome:
    schema = notes_schema(enabled_extras(conf))
    reasons: list[str] = []
    resume: list[datetime] = []
    for label, make in providers:
        try:
            provider: LLMProvider = make()
        except (LLMUnavailable, LLMLimit) as exc:
            reasons.append(f"{label}: {exc}")
            rep.warn(f"Notes provider {label} unavailable: {exc}")
            continue
        attempts, message, problems = [], user, []
        for attempt in (1, 2):
            rep.info(f"Notes: {label}, sections {batch[0].index}–{batch[-1].index}"
                     + (" (retry)" if attempt == 2 else ""))
            try:
                result: LLMResult = provider.generate(system, message, schema)
            except LLMLimit as exc:
                reasons.append(f"{label}: {exc}")
                if exc.resume_at:
                    resume.append(exc.resume_at)
                rep.warn(f"{label}: {exc}")
                break
            except LLMUnavailable as exc:
                reasons.append(f"{label}: {exc}")
                rep.warn(f"{label}: {exc}")
                break
            except LLMBadOutput as exc:
                attempts.append({"error": str(exc)})
                rep.warn(f"{label}: {exc}")
                problems = [str(exc)]
                continue
            notes, check = validate(result.data, batch, conf.notes.ts_tolerance_s)
            attempts.append({"model": result.model, "input_tokens": result.input_tokens,
                             "output_tokens": result.output_tokens, "elapsed_s": result.elapsed_s,
                             "fatal": check.fatal, "dropped": check.dropped, "raw": result.raw, "data": result.data})
            only_hints = notes is not None and check.fatal and all(p.startswith("exam-hint") for p in check.fatal)
            if not check.fatal or (attempt == 2 and only_hints):
                flags = []
                if check.missing_hints:
                    add_missing_hints(notes, batch, check.missing_hints)
                    flags.append(f"{len(check.missing_hints)} exam hints added from the transcript (LLM dropped them)")
                return BatchOutcome(notes, {"provider": label, "model": result.model, "attempts": attempts,
                                            "dropped": check.dropped, "flags": flags,
                                            "notes": notes.model_dump()})
            problems = check.fatal
            rep.warn(f"{label}: answer rejected: {'; '.join(problems)[:300]}")
            message = user + "\n\n# Your previous answer was rejected\n" + "\n".join(f"- {p}" for p in problems) \
                + "\nAnswer again, fixing these problems.\n"
        else:
            reasons.append(f"{label}: no valid answer after 2 attempts ({'; '.join(problems)[:200]})")
    raise NotesPending(reasons, min(resume) if resume else None)


def merge(outcomes: list[LectureNotes]) -> LectureNotes:
    if len(outcomes) == 1:
        return outcomes[0]
    seen, glossary = set(), []
    for n in outcomes:
        for g in n.glossary:
            if g.term.lower() not in seen:
                seen.add(g.term.lower())
                glossary.append(g)
    return LectureNotes(sections=[s for n in outcomes for s in n.sections],
                        summary="\n\n".join(n.summary for n in outcomes), glossary=glossary,
                        quiz=[q for n in outcomes for q in n.quiz],
                        flashcards=[f for n in outcomes for f in n.flashcards])


def make_notes(notes_dir: Path, inputs: list[SectionInput], heading: str, course: Course, conf: Config,
               providers: list[tuple[str, callable]], rep: Reporter) -> tuple[LectureNotes, list[dict]]:
    """All batches (finished ones are reused from notes_dir); returns merged notes and per-batch records."""
    batches = make_batches(inputs, conf.notes.max_input_tokens_per_call)
    extras = enabled_extras(conf)
    system = system_prompt(course, len(batches), extras)
    results, records = [], []
    for i, batch in enumerate(batches, start=1):
        user = user_message(heading, course, batch, (i, len(batches)))
        h = hash_data({"system": system, "user": user, "schema": notes_schema(extras)})
        path = notes_dir / f"batch_{i:02d}.json"
        if path.exists() and read_json(path).get("input_hash") == h:
            record = read_json(path)
            results.append(LectureNotes.model_validate(record["notes"]))
            records.append(record)
            continue
        outcome = run_batch(providers, system, user, batch, conf, rep)
        record = {"input_hash": h, "time": datetime.now().isoformat(timespec="seconds"),
                  "sections": [s.index for s in batch], **outcome.record}
        write_json(path, record)
        results.append(outcome.notes)
        records.append(record)
    return merge(results), records


def load_notes(notes_dir: Path) -> LectureNotes | None:
    """The merged notes of a job from its saved batches (None when no notes were made yet)."""
    batches = sorted(notes_dir.glob("batch_*.json")) if notes_dir.exists() else []
    if not batches:
        return None
    return merge([LectureNotes.model_validate(read_json(p)["notes"]) for p in batches])


# --- outputs ----------------------------------------------------------------------------------------------

_L = {
    "nl": {"summary": "Samenvatting", "slide": "Op de slide", "lecturer": "Uitleg van de docent",
           "definitions": "Definities", "examples": "Voorbeelden", "exam": "Examentips", "glossary": "Begrippenlijst",
           "quiz": "Quiz", "answers": "Antwoorden", "options": "Opties", "notes": "Notities"},
    "en": {"summary": "Summary", "slide": "On the slide", "lecturer": "Lecturer's explanation",
           "definitions": "Definitions", "examples": "Examples", "exam": "Exam hints", "glossary": "Glossary",
           "quiz": "Quiz", "answers": "Answers", "options": "Options", "notes": "Notes"},
}


def _ts(ts: str) -> str:
    return f"[{fmt_ts(parse_ts(ts))}]"


def render_outputs(notes: LectureNotes, inputs: list[SectionInput], heading: str, lang: str,
                   tags: str, extras: set[str] | frozenset[str] = frozenset(EXTRAS)) -> dict[str, str]:
    """Output files; optional extras only when switched on (and present in the notes)."""
    L = _L[lang]
    by_index = {s.index: s for s in inputs}
    md = [f"# {L['notes']}: {heading}", "", f"## {L['summary']}", "", notes.summary, ""]
    hints = [f"# {L['exam']}: {heading}", ""]
    for sec in notes.sections:
        inp = by_index[sec.index]
        where = f" (slide {inp.pages[0]}" + (f"–{inp.pages[-1]}" if len(inp.pages) > 1 else "") + ")" if inp.pages else ""
        md += [f"## {sec.index}. {sec.title}{where} · {fmt_ts(inp.start)}–{fmt_ts(inp.end)}", ""]
        if sec.slide_summary.strip():
            md += [f"**{L['slide']}:** {sec.slide_summary.strip()}", ""]
        for key, items, fmt in (
            ("lecturer", sec.lecturer_additions, lambda p: f"- {p.text} {_ts(p.ts)}"),
            ("definitions", sec.definitions, lambda d: f"- **{d.term}**: {d.definition} {_ts(d.ts)}"),
            ("examples", sec.examples, lambda p: f"- {p.text} {_ts(p.ts)}"),
            ("exam", sec.exam_hints, lambda h: f"- “{h.quote}” {_ts(h.ts)}"),
        ):
            if items:
                md += [f"**{L[key]}**", ""] + [fmt(x) for x in items] + [""]
        if sec.exam_hints:
            hints += [f"## {sec.index}. {sec.title}", ""] + [f"- “{h.quote}” {_ts(h.ts)}" for h in sec.exam_hints] + [""]
    glossary = [f"# {L['glossary']}: {heading}", ""] + [
        f"- **{g.term}**: {g.definition} {_ts(g.ts)}" for g in sorted(notes.glossary, key=lambda g: g.term.lower())]
    quiz = [f"# {L['quiz']}: {heading}", ""]
    for i, q in enumerate(notes.quiz, start=1):
        quiz.append(f"{i}. {q.q} {_ts(q.ts)}")
        quiz += [f"   - {chr(97 + k)}) {o}" for k, o in enumerate(q.options)]
    quiz += ["", f"## {L['answers']}", ""] + [f"{i}. {q.a}" for i, q in enumerate(notes.quiz, start=1)]
    files = {"notes.md": "\n".join(md) + "\n",
             "summary.md": f"# {L['summary']}: {heading}\n\n{notes.summary}\n"}
    if "glossary" in extras and notes.glossary:
        files["glossary.md"] = "\n".join(glossary) + "\n"
    if "exam_hints" in extras and any(s.exam_hints for s in notes.sections):
        files["exam_hints.md"] = "\n".join(hints) + "\n"
    if "quiz" in extras and notes.quiz:
        files["quiz.md"] = "\n".join(quiz) + "\n"
    if "flashcards" in extras and notes.flashcards:
        files["flashcards_anki.csv"] = anki_csv(notes.flashcards, tags)
    return files


def anki_csv(cards: list[Flashcard], tags: str) -> str:
    """Anki import file: header lines tell Anki the separator and which column holds the tags."""
    buf = io.StringIO()
    buf.write("#separator:Semicolon\n#html:false\n#tags column:3\n")
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    for c in cards:
        writer.writerow([c.front.strip(), f"{c.back.strip()} {_ts(c.ts)}", tags])
    return buf.getvalue()


def study_pack(inputs: list[SectionInput], heading: str, course: Course, conf: Config) -> str:
    """Everything needed to make the notes by hand in a Claude Project: instructions + the lecture input."""
    batches = make_batches(inputs, conf.notes.max_input_tokens_per_call)
    parts = [f"# Study pack: {heading}", "",
             "Paste this whole file into a Claude Project (or a chat) and ask for the notes. The first part "
             "is the instruction the app itself uses; the answer format there is JSON, but in a chat you "
             "can ask for Markdown instead.", "", "---", "", system_prompt(course, 1, enabled_extras(conf)), "---", ""]
    for i, batch in enumerate(batches, start=1):
        parts.append(user_message(heading, course, batch, (i, len(batches))))
    return "\n".join(parts)
