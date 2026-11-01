"""Stage 4: transcribe the chunks of one STT run, sequentially, resuming per chunk."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..config import Config
from ..job import Job
from ..providers.base import STTProvider
from ..report import Reporter
from ..terms import combine_prompt
from ..textnorm import clean_tokens, is_masked
from ..util import read_json, write_json
from .s3_chunk import Chunk, chunks_from_plan, cut_audio, cut_chunk, split_region


def raw_path(run_dir: Path, chunk: Chunk) -> Path:
    return run_dir / f"raw_{chunk.id:03d}.json"


def tail_words(text: str, n: int, min_words: int = 5) -> str:
    """Last n real words, for the next chunk's prompt. Masked ('***') or garbage text is never passed
    on: a '***' prompt makes Whisper continue outputting '***' (seen on a real lecture)."""
    if n <= 0:
        return ""
    words = clean_tokens(text)[-n:]
    return " ".join(words) if len(words) >= min_words else ""


def response_text(response: dict) -> str:
    """Text of the response without masked segments."""
    segs = response.get("segments")
    if segs is None:
        return response.get("text", "")
    return " ".join(s.get("text", "") for s in segs if not is_masked(s.get("text", "")))


def run_chunks(job: Job, run_id: str) -> list[Chunk]:
    """The chunks this run transcribes (a partial run only has the chunks of its time range)."""
    run_dir = job.run_dir(run_id)
    chunks = chunks_from_plan(read_json(run_dir / "chunks.json"))
    selected = job.run_info(run_id).get("chunk_ids")
    return chunks if selected is None else [c for c in chunks if c.id in set(selected)]


def missing_chunks(job: Job, run_id: str) -> list[Chunk]:
    run_dir = job.run_dir(run_id)
    return [c for c in run_chunks(job, run_id) if not raw_path(run_dir, c).exists()]


def transcribe_run(job: Job, conf: Config, run_id: str, stt: STTProvider, reporter: Reporter) -> None:
    run_dir = job.run_dir(run_id)
    audio_dir = run_dir / "audio"
    chunks = run_chunks(job, run_id)
    max_bytes = conf.chunking.max_chunk_mb * 1024 * 1024
    previous_text = ""
    info = job.run_info(run_id)
    run_prompt = info.get("term_prompt", "")  # runs from before Stage 2 have none
    chunk_prompts = info.get("chunk_prompts") or {}  # experiment 8.7a: terms of the slides in each chunk
    carry = bool(info.get("carry_prompt"))  # repeat the term prompt on every 30 s window (Mac only)
    if carry and not getattr(stt, "supports_carry", False):
        raise RuntimeError(f"run {run_id} repeats its prompt per window; '{getattr(stt, 'name', stt)}' can't")
    for i, chunk in enumerate(chunks):
        out = raw_path(run_dir, chunk)
        if out.exists():  # done in an earlier attempt: never redo paid work
            previous_text = response_text(read_json(out)["response"])
            continue
        reporter.progress(i, len(chunks), f"Transcribing chunk {i + 1}/{len(chunks)}")
        audio = audio_dir / chunk.file
        if not audio.exists():
            audio_dir.mkdir(parents=True, exist_ok=True)
            cut_chunk(job.full_audio, chunk, audio)
        size = audio.stat().st_size
        if size > max_bytes:
            raise RuntimeError(f"chunk {chunk.id} is {size / 2**20:.1f} MB (> {conf.chunking.max_chunk_mb} MB); "
                               "lower chunking.target_s and redo the transcribe stage")
        term_prompt = chunk_prompts.get(str(chunk.id), run_prompt)
        prompt = combine_prompt(term_prompt, tail_words(previous_text, conf.transcribe.previous_tail_words))
        extra = {"carry_prompt": term_prompt} if carry and term_prompt else {}
        result = stt.transcribe(audio, chunk.duration, job.language, prompt, **extra)
        write_json(out, {
            "request": {"chunk_id": chunk.id, "start": chunk.start, "end": chunk.end, "model": result.model,
                        "language": job.language, "prompt": prompt, **extra, "attempts": result.attempts,
                        "time": datetime.now().isoformat(timespec="seconds")},
            "response": result.response,
        })
        if getattr(stt, "name", "") == "groq" and result.model != conf.stt.model:
            reporter.warn(f"chunk {chunk.id} used fallback model {result.model}")
        previous_text = response_text(result.response)
        if not conf.chunking.keep_chunk_audio:
            audio.unlink(missing_ok=True)
    reporter.progress(len(chunks), len(chunks), f"Transcribed {len(chunks)} chunks")


# --- repair pass ---------------------------------------------------------------------------------
# Whisper sometimes gets stuck on real speech: it returns '***', an empty segment, or garbage, and the
# following 30 s windows copy that state. Such stretches are re-transcribed alone in short pieces.

REPAIRS_INDEX = "repairs.json"


def _speech_fraction(a: float, b: float, silences: list) -> float:
    silent = sum(max(0.0, min(b, e) - max(a, s)) for s, e in silences)
    return 1.0 - silent / (b - a) if b > a else 0.0


def suspect_spans(chunk: Chunk, response: dict, silences: list, conf: Config) -> list[tuple[float, float, str]]:
    """Absolute (start, end, kind) stretches of a chunk worth re-transcribing.

    kind: masked ('***'), empty (no text), gap (no segment at all), garbled (very low confidence).
    Only where Whisper / the silence map say there is speech.
    """
    tc = conf.transcribe
    found: list[tuple[float, float, str]] = []
    cursor = chunk.keep_start
    for seg in sorted(response.get("segments", []), key=lambda x: x["start"]):
        a = max(chunk.start + seg["start"], chunk.keep_start)
        b = min(chunk.start + seg["end"], chunk.keep_end)
        if b <= a:
            continue
        if a - cursor >= tc.gap_min_s and _speech_fraction(cursor, a, silences) >= 0.5:
            found.append((cursor, a, "gap"))
        cursor = max(cursor, b)
        text = seg.get("text", "").strip()
        speech = (seg.get("no_speech_prob") or 0) < tc.masked_max_no_speech
        if not speech:
            continue
        if is_masked(text):
            kind = "masked"
        elif not text and b - a >= 2.0:
            kind = "empty"
        elif text and (seg.get("avg_logprob") or 0) < tc.retry_below_logprob:
            kind = "garbled"
        else:
            continue
        if b - a >= 0.2:
            found.append((a, b, kind))
    if chunk.keep_end - cursor >= tc.gap_min_s and _speech_fraction(cursor, chunk.keep_end, silences) >= 0.5:
        found.append((cursor, chunk.keep_end, "gap"))

    merged: list[list] = []
    for a, b, kind in sorted(found):
        if merged and a - merged[-1][1] < 2.0:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2].add(kind)
        else:
            merged.append([a, b, {kind}])
    # one label per span; "garbled" only if nothing worse is in it
    return [(a, b, "garbled" if kinds == {"garbled"} else "lost") for a, b, kinds in merged]


def repair_pieces(chunk: Chunk, span: tuple[float, float], silences: list, conf: Config) -> list[Chunk]:
    """Pieces of ≤ ~repair_piece_s owning exactly `span`, with padded audio for context."""
    tc = conf.transcribe
    cfg = conf.chunking.model_copy(update={"target_s": tc.repair_piece_s,
                                           "search_window_s": min(10.0, tc.repair_piece_s / 5),
                                           "min_chunk_s": 5.0})
    pieces = []
    for _, _, ks, ke, _ in split_region(span[0], span[1], silences, cfg):
        start = max(chunk.start, ks - tc.repair_padding_s)
        end = min(chunk.end, ke + tc.repair_padding_s)
        pieces.append(Chunk(chunk.id, round(start, 3), round(end, 3), round(ks, 3), round(ke, 3), False))
    return pieces


def _mean_logprob(segments: list[dict]) -> float | None:
    vals = [(s["end"] - s["start"], s.get("avg_logprob")) for s in segments
            if s.get("avg_logprob") is not None and s.get("text", "").strip()]
    total = sum(d for d, _ in vals)
    return sum(d * lp for d, lp in vals) / total if total > 0 else None


def judge_repair(kind: str, new: dict, old_segments: list[dict]) -> tuple[bool, str]:
    """Use the repair only if it's better than what we had."""
    segs = new.get("segments", [])
    texts = [s.get("text", "").strip() for s in segs]
    if not any(texts) or any(is_masked(t) for t in texts):
        return False, "repair also masked/empty"
    if kind == "lost":
        return True, "recovered lost speech"
    old_lp, new_lp = _mean_logprob(old_segments), _mean_logprob(segs)
    if old_lp is None or (new_lp is not None and new_lp > old_lp):
        return True, f"confidence {old_lp:.2f} → {new_lp:.2f}" if old_lp is not None else "ok"
    return False, f"not better ({old_lp:.2f} vs {new_lp:.2f})" if new_lp is not None else "not better"


def repair_run(job: Job, conf: Config, run_id: str, stt: STTProvider, reporter: Reporter) -> list[tuple[float, float]]:
    """Repair suspect stretches of a run (resumable). Returns lost stretches that are still lost."""
    run_dir = job.run_dir(run_id)
    silences = [tuple(s) for s in read_json(job.silences_path)["silences"]]
    used: list[str] = []
    unrepaired: list[tuple[float, float]] = []
    for chunk in run_chunks(job, run_id):
        path = raw_path(run_dir, chunk)
        if not path.exists():
            continue
        response = read_json(path)["response"]
        for a, b, kind in suspect_spans(chunk, response, silences, conf):
            for piece in repair_pieces(chunk, (a, b), silences, conf):
                name = f"repair_{chunk.id:03d}_{int(piece.keep_start * 1000):09d}_{int(piece.keep_end * 1000):09d}.json"
                out = run_dir / name
                if out.exists():
                    data = read_json(out)
                else:
                    reporter.info(f"Re-transcribing {kind} stretch {piece.keep_start / 60:.1f}–{piece.keep_end / 60:.1f} min")
                    audio = run_dir / "audio" / name.replace(".json", ".flac")
                    audio.parent.mkdir(parents=True, exist_ok=True)
                    cut_audio(job.full_audio, piece.start, piece.end, audio)
                    result = stt.transcribe(audio, piece.duration, job.language, "")
                    old = [s for s in response.get("segments", [])
                           if piece.keep_start <= chunk.start + (s["start"] + s["end"]) / 2 < piece.keep_end]
                    ok, why = judge_repair(kind, result.response, old)
                    if (not ok and kind == "lost" and getattr(stt, "name", "") == "groq"
                            and result.model != conf.stt.fallback_model):
                        result = stt.transcribe(audio, piece.duration, job.language, "", model=conf.stt.fallback_model)
                        ok, why = judge_repair(kind, result.response, old)
                    data = {
                        "request": {"chunk_id": chunk.id, "start": piece.start, "end": piece.end,
                                    "keep_start": piece.keep_start, "keep_end": piece.keep_end, "kind": kind,
                                    "model": result.model, "language": job.language, "prompt": "",
                                    "attempts": result.attempts, "time": datetime.now().isoformat(timespec="seconds")},
                        "response": result.response,
                        "accepted": ok,
                        "reason": why,
                    }
                    write_json(out, data)
                    if not conf.chunking.keep_chunk_audio:
                        audio.unlink(missing_ok=True)
                used.append(name)
                if not data["accepted"] and kind == "lost":
                    unrepaired.append((piece.keep_start, piece.keep_end))
        write_json(run_dir / REPAIRS_INDEX, {"version": 2, "files": used})
    write_json(run_dir / REPAIRS_INDEX, {"version": 2, "files": used})
    return unrepaired


def repair_files(run_dir: Path, chunk_id: int) -> list[Path]:
    """Accepted-or-not repair files of the current repair plan for one chunk."""
    index = run_dir / REPAIRS_INDEX
    if not index.exists():
        return []
    prefix = f"repair_{chunk_id:03d}_"
    return [run_dir / f for f in read_json(index)["files"] if f.startswith(prefix) and (run_dir / f).exists()]
