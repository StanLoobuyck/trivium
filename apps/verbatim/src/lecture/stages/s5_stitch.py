"""Stage 5: stitch chunk transcripts into one timeline and filter Whisper hallucinations."""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from ..config import StitchConfig
from ..textnorm import is_masked, normalize_text, normalize_words
from ..util import read_json
from .s3_chunk import Chunk
from .s4_transcribe import raw_path, repair_files

Segment = dict[str, Any]


def _mid(item: dict) -> float:
    return (item["start"] + item["end"]) / 2


def _assign_words(segments: list[dict], words: list[dict]) -> list[list[dict]]:
    """Word lists per segment, by word midpoint (nearest segment if it falls in a gap)."""
    per_seg: list[list[dict]] = [[] for _ in segments]
    if not segments:
        return per_seg
    for w in words:
        m = _mid(w)
        best = min(range(len(segments)), key=lambda i: 0.0 if segments[i]["start"] <= m < segments[i]["end"]
                   else min(abs(m - segments[i]["start"]), abs(m - segments[i]["end"])))
        per_seg[best].append(w)
    return per_seg


def chunk_segments(chunk: Chunk, raw: dict) -> list[Segment]:
    """Segments of one chunk in absolute time, trimmed to the chunk's owned range."""
    resp = raw["response"]
    off = chunk.start
    segs = [dict(s, start=s["start"] + off, end=s["end"] + off) for s in resp.get("segments", [])]
    words = [{"word": w["word"].strip(), "start": w["start"] + off, "end": w["end"] + off}
             for w in resp.get("words", []) if w.get("word", "").strip()]
    per_seg = _assign_words(segs, words)
    out: list[Segment] = []
    for seg, seg_words in zip(segs, per_seg):
        text = seg.get("text", "").strip()
        base = {
            "start": seg["start"], "end": seg["end"], "text": text, "chunk": chunk.id,
            "avg_logprob": seg.get("avg_logprob"), "no_speech_prob": seg.get("no_speech_prob"),
            "compression_ratio": seg.get("compression_ratio"), "flags": [], "words": seg_words,
        }
        if not seg_words:
            if chunk.keep_start <= _mid(seg) < chunk.keep_end:
                out.append(base)
            continue
        kept = [w for w in seg_words if chunk.keep_start <= _mid(w) < chunk.keep_end]
        if len(kept) == len(seg_words):
            out.append(base)
        elif kept:  # segment crosses a hard cut: rebuild it from the words we own
            base.update(start=kept[0]["start"], end=kept[-1]["end"], words=kept,
                        text=" ".join(w["word"] for w in kept), flags=["seam_trimmed"])
            out.append(base)
    return [s for s in out if s["text"]]


def dedupe_seam(prev: Segment, nxt: Segment, lang: str, max_words: int = 10) -> None:
    """Remove words at the start of `nxt` that repeat the end of `prev` (overlap seam)."""
    a, b = normalize_words(prev["text"], lang), normalize_words(nxt["text"], lang)
    raw_tokens = nxt["text"].split()
    for k in range(min(max_words, len(a), len(b), len(raw_tokens)), 1, -1):
        if fuzz.ratio(" ".join(a[-k:]), " ".join(b[:k])) >= 90:
            nxt["text"] = " ".join(raw_tokens[k:])
            if nxt["words"]:
                nxt["words"] = nxt["words"][k:]
                if nxt["words"]:
                    nxt["start"] = nxt["words"][0]["start"]
            nxt["flags"].append("seam_deduped")
            return


def collapse_repetitions(text: str, max_n: int = 8, min_repeats: int = 3) -> tuple[str, bool]:
    """'a b a b a b a b c' → 'a b c' for n-grams repeated ≥ min_repeats times in a row."""
    tokens = text.split()
    norm = [t.lower().strip(".,!?;:") for t in tokens]
    changed = False
    for n in range(1, max_n + 1):
        i = 0
        while i + n * min_repeats <= len(tokens):
            gram = norm[i:i + n]
            reps = 1
            while norm[i + reps * n:i + (reps + 1) * n] == gram:
                reps += 1
            if reps >= min_repeats:
                del tokens[i + n:i + reps * n]
                del norm[i + n:i + reps * n]
                changed = True
            i += 1
    return " ".join(tokens), changed


def filter_segment(seg: Segment, prompt: str, cfg: StitchConfig, lang: str, chunk_start: float) -> str | None:
    """Apply hallucination rules. Returns a removal reason, or None (segment kept, maybe flagged)."""
    if is_masked(seg["text"]):
        return "masked"
    norm = normalize_text(seg["text"], lang)
    if not norm:
        return "empty"
    if any(norm == normalize_text(p, lang) for p in cfg.phantom_exact):
        return "phantom"
    if any(norm.startswith(normalize_text(p, lang)) for p in cfg.phantom_prefix):
        return "phantom"
    norm_prompt = normalize_text(prompt, lang) if prompt else ""
    # Prompt echo: Whisper repeats its prompt at the start of a chunk or on near-silence. Only check
    # there, and only for segments of ≥ 6 words, so a lecturer repeating a phrase isn't removed.
    suspicious = seg["start"] - chunk_start < 30 or (seg["no_speech_prob"] or 0) > 0.3
    if (norm_prompt and suspicious and len(norm.split()) >= 6
            and fuzz.partial_ratio(norm, norm_prompt) > cfg.prompt_echo_ratio):
        return "prompt_echo"
    if (seg["compression_ratio"] or 0) > cfg.compression_ratio:
        seg["text"], changed = collapse_repetitions(seg["text"])
        seg["flags"].append("repetition_collapsed" if changed else "high_compression")
    if (seg["no_speech_prob"] or 0) > cfg.no_speech_prob and (seg["avg_logprob"] or 0) < cfg.no_speech_logprob:
        seg["flags"].append("likely_no_speech")
    if seg["avg_logprob"] is not None and seg["avg_logprob"] < cfg.low_confidence_logprob:
        seg["flags"].append("low_confidence")
    return None


def _duplicated_near(seg: Segment, piece: Chunk, new_text: str, lang: str, margin_s: float = 5.0) -> bool:
    """An original segment just outside a repaired piece whose text the repair already contains.

    Whisper squeezes timestamps when it gets stuck, so an original segment can claim 0.7 s for a
    sentence that really lies inside the repaired stretch.
    """
    if seg["end"] < piece.keep_start - margin_s or seg["start"] > piece.keep_end + margin_s:
        return False
    norm = normalize_text(seg["text"], lang)
    return len(norm.split()) >= 4 and fuzz.partial_ratio(norm, new_text) >= 85


def with_repairs(segs: list[Segment], chunk: Chunk, run_dir, lang: str) -> list[Segment]:
    """Replace the parts of a chunk that were re-transcribed by the repair pass."""
    for path in repair_files(run_dir, chunk.id):
        rep = read_json(path)
        req = rep["request"]
        piece = Chunk(chunk.id, req["start"], req["end"], req["keep_start"], req["keep_end"], False)
        if not rep.get("accepted"):
            continue  # repair wasn't better: keep the original (masked → removed and reported)
        new = chunk_segments(piece, rep)
        for n in new:
            n["flags"].append("repaired")
        new_text = normalize_text(" ".join(n["text"] for n in new), lang)
        segs = [x for x in segs
                if not piece.keep_start <= _mid(x) < piece.keep_end
                and not _duplicated_near(x, piece, new_text, lang)] + new
    return sorted(segs, key=lambda x: x["start"])


def stitch(chunks: list[Chunk], run_dir, cfg: StitchConfig, lang: str) -> dict:
    """Stitch whatever chunks of this run have a raw response (partial runs are fine)."""
    segments: list[Segment] = []
    removed: list[Segment] = []
    prev_chunk: Chunk | None = None
    for chunk in chunks:
        path = raw_path(run_dir, chunk)
        if not path.exists():
            prev_chunk = None
            continue
        raw = read_json(path)
        segs = with_repairs(chunk_segments(chunk, raw), chunk, run_dir, lang)
        # hard cut between the two chunks: their audio files overlap
        if segs and segments and prev_chunk is not None and prev_chunk.end > chunk.start + 1e-6:
            dedupe_seam(segments[-1], segs[0], lang)
        prompt = raw["request"].get("prompt", "")
        for seg in segs:
            reason = filter_segment(seg, prompt, cfg, lang, chunk.start)
            if reason:
                removed.append({**seg, "reason": reason})
            elif seg["text"]:
                segments.append(seg)
        prev_chunk = chunk
    for i, seg in enumerate(segments):
        seg["id"] = i
    return {"segments": segments, "removed": removed}
