"""Experiment 8.7c (PLAN.md Phase 8): a local LLM (Ollama on the Mac) proposes term fixes per part of a lecture.

    uv run python scripts/exp_llmfix.py JOB_DIR [--run rN] [--llm MODEL ...] [--ollama URL] [--refs REFS.yaml]

Per part (a section of sections.json, split into windows of at most --window s) the model gets the slides on
screen + that part's transcript and returns {wrong, right} pairs. Code keeps a pair only when
  - `wrong` occurs in that window's text (whole words), and
  - every word of `right` is on the slides of that part, in the term list, or already in `wrong`, and at least
    one word of `right` is a slide/term word that `wrong` doesn't have (so no rephrasing, no common-word swaps),
  - `wrong` has a word that is uncommon in the lecture's language (not "of", "nog", single letters), and
  - `wrong` and `right` sound alike (fixes.skeleton, ratio ≥ SOUND_MIN): no "aritmetisch" → "logisch".
Verdicts are recomputed from the cached answers on every run, so changing these rules needs no LLM calls.
The run itself is never changed: answers + verdicts go to stt/<run>/llmfix_<model>.json (cached per window,
re-run to resume). With references for this job (refs.yaml) it prints WER/term recall for
raw / rules (fixes.py) / llm / rules+llm.
"""

from __future__ import annotations

import argparse
import copy
import difflib
import re
import sys
import time
from pathlib import Path

import yaml

from exp_prompts import ollama_json, slide_text  # same folder
from lecture import config as cfgmod
from lecture import fixes
from lecture.evaluate import evaluate, hypothesis_text, pooled, read_reference
from lecture.job import Job
from lecture.pipeline import job_course, stitch_run
from lecture.textnorm import normalize_words
from lecture.util import parse_ts, read_json, write_json

FIX_PROMPT = """Hieronder staat een stuk automatische transcriptie (Whisper) van een les "{course}", met de tekst \
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
SOUND_MIN = 0.6


def windows(job: Job, segments: list[dict], max_s: float) -> list[dict]:
    """Parts of the lecture: sections split into ≤ max_s windows, each with its slides and segment indices."""
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


def ask(url: str, model: str, course: str, slides: list[dict], text: str) -> list[dict]:
    prompt = FIX_PROMPT.format(course=course, text=text,
                               slides="\n\n---\n\n".join(slide_text(s) for s in slides) or "(geen)")
    pairs = ollama_json(url, model, prompt).get("fixes") or []
    return [p for p in pairs if isinstance(p, dict) and isinstance(p.get("wrong"), str)
            and isinstance(p.get("right"), str)]


def _pattern(wrong: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(wrong.strip())}(?!\w)", re.IGNORECASE)


def verdict(pair: dict, text: str, vocab: set[str], lang: str) -> str:
    """'ok' or why the pair is refused."""
    wrong, right = pair["wrong"].strip(), pair["right"].strip()
    if not wrong or not right or wrong.lower() == right.lower():
        return "empty/same"
    if not _pattern(wrong).search(text):
        return "not in text"
    w, r = set(normalize_words(wrong, lang)), normalize_words(right, lang)
    if any(x not in vocab and x not in w for x in r):
        return "not a slide term"
    if not any(x in vocab and x not in w for x in r):
        return "adds no term"
    from wordfreq import zipf_frequency

    if all(len(x) < 2 or zipf_frequency(x.lower(), lang) >= COMMON_ZIPF for x in re.findall(r"[^\W_]+", wrong)):
        return "common words"
    sw, sr = ("".join(fixes.skeleton(t) for t in x.split()) for x in (wrong, right))
    if difflib.SequenceMatcher(None, sw, sr).ratio() < SOUND_MIN:
        return "doesn't sound alike"
    return "ok"


def apply(segments: list[dict], wins: list[dict], answers: dict) -> list[dict]:
    segs = copy.deepcopy(segments)
    for win in wins:
        for pair in answers.get(win["key"], {}).get("fixes", []):
            if pair["verdict"] == "ok":
                pat = _pattern(pair["wrong"])
                for j in win["segments"]:
                    segs[j]["text"] = pat.sub(pair["right"].strip(), segs[j]["text"])
    return segs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("--run", help="default: the job's main run")
    ap.add_argument("--llm", action="append", help="repeatable; default qwen3.8:27b and gemma4:26b")
    ap.add_argument("--ollama", default="http://localhost:11435", help="Ollama (ssh -L 11435:localhost:11434 mac)")
    ap.add_argument("--window", type=float, default=300.0, help="max length of one part (s)")
    ap.add_argument("--refs", type=Path, default=Path.home() / "Lectures/references/refs.yaml")
    args = ap.parse_args()
    models = args.llm or ["qwen3.8:27b", "gemma4:26b"]

    conf = cfgmod.load_config()
    job = Job(args.job)
    run_id = args.run or job.current_run
    course = job_course(job)
    lang = job.language
    terms = read_json(job.root / "terms.json")["terms"]
    segments = stitch_run(job, conf, run_id)["segments"]
    wins = windows(job, segments, args.window)
    base_vocab = {w for t in terms for w in normalize_words(t["term"], lang)}
    base_vocab |= {w for v in course.corrections.values() for w in normalize_words(v, lang)}

    results: dict[str, dict] = {}
    for model in models:
        out = job.run_dir(run_id) / f"llmfix_{model.replace(':', '_').replace('/', '_')}.json"
        answers = read_json(out) if out.exists() else {}
        for i, win in enumerate(wins):
            text = " ".join(segments[j]["text"].strip() for j in win["segments"])
            vocab = base_vocab | {w for s in win["slides"] for w in normalize_words(slide_text(s), lang)}
            if win["key"] in answers:
                for f in answers[win["key"]]["fixes"]:
                    f["verdict"] = verdict(f, text, vocab, lang)
                continue
            t0 = time.monotonic()
            pairs = ask(args.ollama, model, course.name, win["slides"], text)
            fixes_ = [{"wrong": p["wrong"], "right": p["right"], "verdict": verdict(p, text, vocab, lang)}
                      for p in pairs]
            answers[win["key"]] = {"start": win["start"], "end": win["end"], "elapsed_s": time.monotonic() - t0,
                                   "fixes": fixes_}
            write_json(out, answers)
            ok = [f"{f['wrong']} → {f['right']}" for f in fixes_ if f["verdict"] == "ok"]
            print(f"{model} part {i + 1}/{len(wins)} ({answers[win['key']]['elapsed_s']:.0f} s): "
                  f"{len(fixes_)} proposed, {len(ok)} kept {ok[:6]}", flush=True)
        write_json(out, answers)
        results[model] = answers
        all_ = [f for a in answers.values() for f in a["fixes"]]
        print(f"\n{model}: {len(all_)} proposed, {sum(f['verdict'] == 'ok' for f in all_)} kept, "
              f"{sum(a['elapsed_s'] for a in answers.values()) / 60:.1f} min LLM time → {out}")
        for f in all_:
            print(f"  [{f['verdict']:<16}] {f['wrong']!r} → {f['right']!r}")

    refs = [r for r in (yaml.safe_load(args.refs.read_text()) if args.refs.exists() else [])
            if Path(args.refs.parent / r["job"]).resolve() == job.root.resolve()]
    if not refs:
        print("\nNo references for this job: no WER table.")
        return
    term_list = [t["term"] for t in terms if t.get("source") != "lecturer"]
    variants = {"raw": segments}
    ruled = copy.deepcopy(segments)
    fixes.apply_fixes(ruled, terms, course.corrections)
    variants["rules"] = ruled
    for model, answers in results.items():
        variants[f"llm {model}"] = apply(segments, wins, answers)
        variants[f"rules+llm {model}"] = apply(ruled, wins, answers)
    print(f"\nRun {run_id}, {len(refs)} reference(s), term recall over {len(term_list)} slide terms")
    print(f"{'variant':<28} {'WER':>7} {'sub':>5} {'del':>5} {'ins':>5}  term recall")
    for name, segs in variants.items():
        res = [evaluate(r["ref"], read_reference(args.refs.parent / r["ref"]),
                        hypothesis_text(segs, parse_ts(str(r["start"])), parse_ts(str(r["end"]))), term_list, lang)
               for r in refs]
        p = pooled(res) if len(res) > 1 else res[0]
        recall = f"{p.term_recall:.0%} ({p.term_hits}/{p.term_total})" if p.term_recall is not None else "–"
        print(f"{name:<28} {p.wer:>7.2%} {p.substitutions:>5} {p.deletions:>5} {p.insertions:>5}  {recall}")


if __name__ == "__main__":
    sys.exit(main())
