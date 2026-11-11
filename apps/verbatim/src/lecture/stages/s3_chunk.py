"""Stage 3: plan chunks at silences, skip long silences, cut chunk audio files.

Chunks are plain cuts of audio/full.flac (never spliced), so absolute time = chunk start + segment
time. Each chunk owns [keep_start, keep_end); with a hard cut (no silence found) the audio file
extends past that by half the overlap on each side, and Stage 5 keeps words by midpoint.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import ChunkingConfig

Interval = tuple[float, float]


@dataclass
class Chunk:
    id: int
    start: float        # audio file range (s, absolute)
    end: float
    keep_start: float   # ownership range for stitching
    keep_end: float
    overlap: bool       # a boundary of this chunk is a hard cut with overlap

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def file(self) -> str:
        return f"{self.id:03d}.flac"


def speech_regions(duration: float, silences: list[Interval], cfg: ChunkingConfig) -> tuple[list[Interval], list[Interval]]:
    """Split [0, duration] at long silences. Returns (regions, skipped ranges).

    The minimum-length check uses the unpadded speech, so a short noise blip between two long
    silences isn't kept just because padding made it look longer.
    """
    pad = cfg.skip_padding_s
    long = [(s, e) for s, e in sorted(silences) if e - s > cfg.skip_silence_over_s]
    raw: list[Interval] = []
    cursor = 0.0
    for s, e in long:
        if s > cursor:
            raw.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        raw.append((cursor, duration))

    regions = [
        (max(0.0, a - pad), min(duration, b + pad))
        for a, b in raw
        if b - a >= cfg.min_region_s
    ]
    regions = _merge(regions)
    skipped: list[Interval] = []
    cursor = 0.0
    for a, b in regions:
        if a > cursor:
            skipped.append((cursor, a))
        cursor = b
    if cursor < duration:
        skipped.append((cursor, duration))
    return regions, skipped


def _merge(intervals: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1] + 1e-6:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def split_region(start: float, end: float, silences: list[Interval], cfg: ChunkingConfig) -> list[tuple[float, float, float, float, bool]]:
    """Cut one speech region into pieces (file_start, file_end, keep_start, keep_end, overlap)."""
    target = cfg.target_s
    window = min(cfg.search_window_s, 0.2 * target)
    half_overlap = cfg.hard_cut_overlap_s / 2
    pieces = []
    keep_start = file_start = start
    overlap_in = False
    while end - keep_start > 1.5 * target:
        t = keep_start + target
        candidates = [
            (b - a, (a + b) / 2)
            for a, b in silences
            if t - window <= (a + b) / 2 <= t + window
            and a >= keep_start + cfg.min_chunk_s and b <= end - cfg.min_chunk_s
        ]
        if candidates:
            cut = max(candidates)[1]
            pieces.append((file_start, cut, keep_start, cut, overlap_in))
            file_start, keep_start, overlap_in = cut, cut, False
        else:
            pieces.append((file_start, t + half_overlap, keep_start, t, True))
            file_start, keep_start, overlap_in = t - half_overlap, t, True
    pieces.append((file_start, end, keep_start, end, overlap_in))
    return pieces


def plan_chunks(duration: float, silences: list[Interval], cfg: ChunkingConfig) -> dict:
    regions, skipped = speech_regions(duration, silences, cfg)
    chunks: list[Chunk] = []
    for a, b in regions:
        for fs, fe, ks, ke, ov in split_region(a, b, silences, cfg):
            chunks.append(Chunk(len(chunks), round(fs, 3), round(fe, 3), round(ks, 3), round(ke, 3), ov))
    return {
        "duration_s": duration,
        "target_s": cfg.target_s,
        "chunks": [asdict(c) for c in chunks],
        "skipped": [[round(a, 3), round(b, 3)] for a, b in skipped],
    }


def chunks_from_plan(plan: dict) -> list[Chunk]:
    return [Chunk(**c) for c in plan["chunks"]]


def select_range(chunks: list[Chunk], start: float, end: float) -> list[Chunk]:
    """Chunks whose owned range overlaps [start, end]."""
    return [c for c in chunks if c.keep_end > start and c.keep_start < end]


def cut_audio(full_audio: Path, start: float, end: float, out: Path) -> None:
    """Sample-accurate 16-bit FLAC cut (input-side -ss is accurate when re-encoding).

    asetnsamples: after some seeks the decoder's first frame is tiny (e.g. 10 samples) and the FLAC
    encoder refuses to start ("invalid block size") — fixed frame sizes avoid that.
    """
    part = out.with_name(out.name + ".part")
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start:.3f}", "-i", str(full_audio), "-t", f"{end - start:.3f}",
         "-af", "asetnsamples=n=4096:p=0,aformat=sample_fmts=s16",
         "-c:a", "flac", "-f", "flac", str(part)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg could not cut {start:.1f}–{end:.1f} s: {proc.stderr.strip()[-500:]}")
    part.replace(out)


def cut_chunk(full_audio: Path, chunk: Chunk, out: Path) -> None:
    cut_audio(full_audio, chunk.start, chunk.end, out)
