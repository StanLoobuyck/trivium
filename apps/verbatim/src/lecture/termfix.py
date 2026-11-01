"""Term fix suggestions from a local LLM on the Mac (PLAN.md 8.7c, measured 2026-10-25, see CHANGELOG).

After transcription, per part of the lecture (a section of sections.json, split into ≤ termfix.window_s) the
model gets the slides on screen + that part's transcript and proposes wrong → right pairs. Code keeps a pair
only when
  - `wrong` occurs in that part (whole words),
  - every word of `right` is on that part's slides, in the term list or already in `wrong`, and one of them
    is a slide/term word that `wrong` lacks (no rephrasing),
  - `wrong` has a word that is uncommon in the lecture's language ("end"/"off" yes, "of"/"nog"/"N" no), and
  - both sound alike (fixes.skeleton): no "aritmetisch" → "logisch".
Nothing changes by itself: the user accepts a suggestion (applied in the stitch stage, only within its part),
rejects it, or adds it to the course fix list (every occurrence, every lecture). AND/NAND and OR/NOR choices
are the reason it isn't automatic.

termfix.json in the job: {run, model, status: running|done|failed|skipped, error, made, elapsed_s, proposed,
refused: {reason: n}, answers: {part key: raw pairs} (resume), suggestions: [{id, start, end, at, wrong, right,
count, context, status: open|accepted|rejected|course}]}.
"""

from __future__ import annotations

import copy
import difflib
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from . import fixes
from .job import Job
from .report import NullReporter, Reporter
from .textnorm import normalize_words
from .util import read_json, write_json

PROMPT = """Hieronder staat een stuk automatische transcriptie (Whisper) van een les "{course}", met de tekst \
van de slides die de docent op dat moment toont. Whisper schrijft vaktermen vaak fout (bv. "nent" voor NAND, \
"ELU" voor ALU).
Zoek in de transcriptie woorden of woordgroepen die een verkeerd gehoorde vakterm van de slides zijn. Geef per \
fout: "wrong" = exact zoals het in de transcriptie staat, "right" = de term zoals gespeld op de slides.
Alleen echte hoorfouten van vaktermen; geen grammatica, geen stijl, geen gewone woorden die kloppen. Geen fouten \
gevonden: lege lijst.
Antwoord alleen met JSON: {{"fixes": [{{"wrong": "...", "right": "..."}}]}}

Slides:
{slides}

Transcriptie:
{text}"""

COMMON_ZIPF = 5.0  # "end" (4.3) and "off" (4.4) are real mishearings of AND/OR; "of" (6.5) never is
SOUND_MIN = 0.6    # fixes.skeleton similarity; "aritmetisch" → "logisch" is 0.56
STATUSES = ("open", "accepted", "rejected", "course")


def path(job: Job) -> Path:
    return job.root / "termfix.json"


def load(job: Job) -> dict | None:
    p = path(job)
    return read_json(p) if p.exists() else None


def slide_text(s: dict) -> str:
    return f"{s.get('title') or ''}\n{s['text']}\n{s.get('notes') or ''}".strip()


def parts(job: Job, segments: list[dict], max_s: float) -> list[dict]:
    """Sections split into ≤ max_s parts, each with its slides and the indices of its segments (by midpoint)."""
    slides = {(s["file"], int(s["page"])): s for s in read_json(job.slides_dir / "slides.json")["slides"]}
    out = []
    for sec in read_json(job.root / "sections.json")["sections"]:
        shown = [slides[k] for r in sec["slides"] if (k := (r["file"], int(r["page"]))) in slides]
        n = max(1, round((sec["end"] - sec["start"]) / max_s + 0.49))
        step = (sec["end"] - sec["start"]) / n
        for i in range(n):
            a, b = sec["start"] + i * step, sec["start"] + (i + 1) * step
            idx = [j for j, s in enumerate(segments) if a <= (s["start"] + s["end"]) / 2 < b]
            if idx:
                out.append({"key": f"{a:.1f}-{b:.1f}", "start": a, "end": b, "slides": shown, "segments": idx})
    return out


def pattern(wrong: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(wrong.strip())}(?!\w)", re.IGNORECASE)


def verdict(wrong: str, right: str, text: str, vocab: set[str], lang: str) -> str:
    """'ok' or why the pair is refused."""
    from wordfreq import zipf_frequency

    wrong, right = wrong.strip(), right.strip()
    if not wrong or not right or wrong.lower() == right.lower():
        return "empty/same"
    if not pattern(wrong).search(text):
        return "not in text"
    w, r = set(normalize_words(wrong, lang)), normalize_words(right, lang)
    if any(x not in vocab and x not in w for x in r):
        return "not a slide term"
    if not any(x in vocab and x not in w for x in r):
        return "adds no term"
    if all(len(x) < 2 or zipf_frequency(x.lower(), lang) >= COMMON_ZIPF for x in re.findall(r"[^\W_]+", wrong)):
        return "common words"
    sw, sr = ("".join(fixes.skeleton(t) for t in x.split()) for x in (wrong, right))
    if difflib.SequenceMatcher(None, sw, sr).ratio() < SOUND_MIN:
        return "doesn't sound alike"
    return "ok"


def _context(text: str, wrong: str, width: int = 60) -> str:
    m = pattern(wrong).search(text)
    if not m:
        return ""
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("…" if a else "") + text[a:b].strip() + ("…" if b < len(text) else "")


def suggest(job: Job, conf, llm, course, rep: Reporter | None = None, fresh: bool = False) -> dict:
    """Ask `llm` (MacLlm-like: model, chat_json(prompt)) part by part; writes and returns termfix.json.
    Resumes from the answers already stored for the same run and model, unless `fresh` (the user's "make them
    again": ask the model anew). The user's decisions (accepted / rejected / whole course) on the same
    transcript are kept either way: accepted words are already fixed in the text, so the model can't propose
    them again, and a rejected suggestion doesn't come back."""
    rep = rep or NullReporter()
    tr = read_json(job.root / "transcript_raw.json")
    segments, lang = tr["segments"], job.language
    old = load(job) or {}
    same_run = old.get("run") == tr["run"]
    decided = [x for x in old.get("suggestions", []) if x["status"] != "open"] if same_run else []
    resume = same_run and old.get("model") == llm.model and not fresh
    data: dict[str, Any] = {"run": tr["run"], "model": llm.model, "status": "running", "error": None,
                            "made": None, "elapsed_s": old.get("elapsed_s", 0.0) if resume else 0.0,
                            "proposed": 0, "refused": {}, "answers": old.get("answers", {}) if resume else {},
                            "suggestions": decided}
    if not (job.slides_dir / "slides.json").exists() or not (job.root / "sections.json").exists():
        data.update(status="skipped", error="no slides")
        write_json(path(job), data)
        return data
    terms = read_json(job.root / "terms.json")["terms"] if (job.root / "terms.json").exists() else []
    base = {w for t in terms for w in normalize_words(t["term"], lang)}
    base |= {w for v in course.corrections.values() for w in normalize_words(v, lang)}
    todo = parts(job, segments, conf.termfix.window_s)
    write_json(path(job), data)
    t0 = time.monotonic()
    found: dict[tuple[str, str, str], dict] = {}
    seen = {(f"{x['start']:.1f}", x["wrong"].lower(), x["right"]) for x in decided}
    next_id = max((int(x["id"][1:]) for x in decided), default=0)
    refused: Counter[str] = Counter()
    for i, part in enumerate(todo):
        rep.progress(i, len(todo), f"term suggestions: part {i + 1}/{len(todo)}")
        text = " ".join(segments[j]["text"].strip() for j in part["segments"])
        if part["key"] not in data["answers"]:
            answer = llm.chat_json(PROMPT.format(course=course.name, text=text, slides="\n\n---\n\n".join(
                slide_text(s) for s in part["slides"]) or "(geen)"))
            pairs = [p for p in answer.get("fixes") or []
                     if isinstance(p, dict) and isinstance(p.get("wrong"), str) and isinstance(p.get("right"), str)]
            data["answers"][part["key"]] = [{"wrong": p["wrong"], "right": p["right"]} for p in pairs]
            write_json(path(job), data)
        vocab = base | {w for s in part["slides"] for w in normalize_words(slide_text(s), lang)}
        for p in data["answers"][part["key"]]:
            data["proposed"] += 1
            v = verdict(p["wrong"], p["right"], text, vocab, lang)
            if v != "ok":
                refused[v] += 1
                continue
            key = (part["key"], p["wrong"].strip().lower(), p["right"].strip())
            if key in found or (f"{round(part['start'], 2):.1f}", key[1], key[2]) in seen:
                continue
            pat = pattern(p["wrong"])
            hits = [j for j in part["segments"] if pat.search(segments[j]["text"])]
            found[key] = {"id": f"s{next_id + len(found) + 1}", "start": round(part["start"], 2),
                          "end": round(part["end"], 2),
                          "at": segments[hits[0]]["start"], "wrong": p["wrong"].strip(), "right": p["right"].strip(),
                          "count": sum(len(pat.findall(segments[j]["text"])) for j in hits),
                          "context": _context(segments[hits[0]]["text"], p["wrong"]), "status": "open"}
    data.update(status="done", made=datetime.now().isoformat(timespec="seconds"),
                elapsed_s=round(data["elapsed_s"] + time.monotonic() - t0, 1),
                refused=dict(refused), suggestions=decided + list(found.values()))
    write_json(path(job), data)
    rep.info(f"Term suggestions ({llm.model}): {len(found)} to review, {sum(refused.values())} refused")
    return data


def mark(job: Job, status: str, error: str) -> None:
    """Record why no suggestions were made (Mac away, LLM error); keeps answers for a later resume."""
    data = load(job) or {"answers": {}, "suggestions": []}
    data.update(status=status, error=error[:300])
    write_json(path(job), data)


def accepted(job: Job) -> list[dict]:
    data = load(job)
    return [s for s in (data or {}).get("suggestions", []) if s["status"] == "accepted"]


def apply_accepted(segments: list[dict], suggestions: list[dict]) -> list[dict[str, Any]]:
    """Apply accepted suggestions in place, each only to segments whose midpoint lies in its part.
    Returns fix-report entries (kind "suggestion") like fixes.apply_fixes."""
    counts: Counter[tuple[str, str]] = Counter()
    for s in suggestions:
        pat, right = pattern(s["wrong"]), s["right"]
        for seg in segments:
            if s["start"] <= (seg["start"] + seg["end"]) / 2 < s["end"]:
                seg["text"], n = pat.subn(right, seg["text"])
                counts[(s["wrong"], right)] += n
                for w in seg.get("words") or []:
                    w["word"] = pat.sub(right, w["word"])
    return [{"kind": "suggestion", "from": w, "to": r, "count": n} for (w, r), n in counts.most_common() if n]


def set_status(job: Job, sid: str, status: str) -> dict:
    """Mark one suggestion; returns it. The caller re-stitches (pipeline.refix) when the applied set changed."""
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    data = load(job)
    if not data or data.get("status") != "done":
        raise ValueError("no finished term suggestions for this lecture")
    for s in data["suggestions"]:
        if s["id"] == sid:
            s["status"] = status
            write_json(path(job), data)
            return copy.deepcopy(s)
    raise KeyError(sid)
