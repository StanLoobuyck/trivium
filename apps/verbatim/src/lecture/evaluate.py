"""`lecture eval`: WER and glossary-term recall against hand-made reference transcripts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import jiwer

from .config import Config
from .job import Job
from .subtitles import timed_tokens
from .textnorm import normalize_words


@dataclass
class EvalResult:
    label: str
    ref_words: int
    hyp_words: int
    wer: float
    substitutions: int
    deletions: int
    insertions: int
    term_hits: int
    term_total: int

    @property
    def term_recall(self) -> float | None:
        return self.term_hits / self.term_total if self.term_total else None


def read_reference(path: Path) -> str:
    """Plain text; lines starting with '#' are comments."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return " ".join(line for line in lines if not line.lstrip().startswith("#"))


def hypothesis_text(segments: list[dict], start: float, end: float) -> str:
    """Words whose midpoint lies in [start, end]."""
    tokens = []
    for seg in segments:
        if seg["end"] < start or seg["start"] > end:
            continue
        tokens += [t for t, a, b in timed_tokens(seg) if start <= (a + b) / 2 <= end]
    return " ".join(tokens)


def _count(words: list[str], term: list[str]) -> int:
    n = len(term)
    return sum(1 for i in range(len(words) - n + 1) if words[i:i + n] == term) if n else 0


def term_recall(ref: list[str], hyp: list[str], terms: list[str], lang: str) -> tuple[int, int]:
    """Σ min(hyp count, ref count) and Σ ref count over the terms that occur in the reference."""
    hits = total = 0
    for term in terms:
        t = normalize_words(term, lang)
        r = _count(ref, t)
        if r:
            total += r
            hits += min(r, _count(hyp, t))
    return hits, total


def evaluate(label: str, ref_text: str, hyp_text: str, terms: list[str], lang: str) -> EvalResult:
    ref = normalize_words(ref_text, lang)
    hyp = normalize_words(hyp_text, lang)
    if not ref:
        raise ValueError(f"{label}: reference is empty")
    out = jiwer.process_words(" ".join(ref), " ".join(hyp) if hyp else "")
    hits, total = term_recall(ref, hyp, terms, lang)
    return EvalResult(label, len(ref), len(hyp), out.wer, out.substitutions, out.deletions, out.insertions,
                      hits, total)


def pooled(results: list[EvalResult]) -> EvalResult:
    ref = sum(r.ref_words for r in results)
    errors = sum(r.substitutions + r.deletions + r.insertions for r in results)
    return EvalResult("pooled", ref, sum(r.hyp_words for r in results), errors / ref,
                      sum(r.substitutions for r in results), sum(r.deletions for r in results),
                      sum(r.insertions for r in results), sum(r.term_hits for r in results),
                      sum(r.term_total for r in results))


def job_segments(job: Job, conf: Config, run_id: str | None) -> list[dict]:
    from .pipeline import stitch_run

    run_id = run_id or job.current_run
    if run_id is None:
        raise ValueError(f"{job.root} has no transcription run yet")
    if run_id not in job.manifest["stt"]["runs"]:
        raise ValueError(f"unknown run {run_id}; runs: {', '.join(job.manifest['stt']['runs'])}")
    return stitch_run(job, conf, run_id)["segments"]


def run_stats(job: Job, conf: Config, run_id: str) -> dict:
    """Summary numbers of one STT run (for provider comparisons)."""
    from .pipeline import stitch_run
    from .stages.s4_transcribe import repair_files, run_chunks
    from .util import read_json

    info = job.run_info(run_id)
    run_dir = job.run_dir(run_id)
    result = stitch_run(job, conf, run_id)
    segs = result["segments"]
    chunks = run_chunks(job, run_id)
    repaired = [read_json(p) for c in chunks for p in repair_files(run_dir, c.id)]
    responses = [read_json(run_dir / f"raw_{c.id:03d}.json")["response"]
                 for c in chunks if (run_dir / f"raw_{c.id:03d}.json").exists()]
    elapsed = [(r.get("x_local") or r.get("x_mac") or {}).get("elapsed_s") for r in responses]
    audio_s = sum(c.keep_end - c.keep_start for c in chunks)
    stt_s = sum(e for e in elapsed if e) if any(elapsed) else None
    return {
        "run": run_id,
        "provider": info.get("provider") or "groq",
        "words": sum(len(s["text"].split()) for s in segs),
        "segments": len(segs),
        "audio_min": audio_s / 60,
        "repaired_min": sum(r["request"]["keep_end"] - r["request"]["keep_start"] for r in repaired
                            if r.get("accepted")) / 60,
        "still_lost": sum(1 for r in repaired if not r.get("accepted") and r["request"].get("kind") == "lost"),
        "low_conf_pct": 100 * sum(1 for s in segs if "low_confidence" in s["flags"]) / max(len(segs), 1),
        "stt_minutes": stt_s / 60 if stt_s else None,
        "segments_list": segs,
    }
