"""SRT/VTT subtitles from timed segments, split into readable cues using word timestamps."""

from __future__ import annotations

from dataclasses import dataclass

from .config import SubtitleConfig


@dataclass
class Cue:
    start: float
    end: float
    text: str


def timed_tokens(seg: dict) -> list[tuple[str, float, float]]:
    """(token, start, end) for each whitespace token of the segment text.

    Uses word timestamps when they line up 1:1 with the text tokens (keeps punctuation from the
    text); otherwise spreads the segment's time over the tokens by character count.
    """
    tokens = seg["text"].split()
    words = seg.get("words") or []
    if words and len(words) == len(tokens):
        return [(t, w["start"], w["end"]) for t, w in zip(tokens, words)]
    total = sum(len(t) + 1 for t in tokens) or 1
    span = seg["end"] - seg["start"]
    out, pos = [], 0
    for t in tokens:
        a = seg["start"] + span * pos / total
        pos += len(t) + 1
        out.append((t, a, seg["start"] + span * pos / total))
    return out


def _greedy_lines(tokens: list[str], width: int) -> list[str]:
    lines: list[str] = []
    for t in tokens:
        if lines and len(lines[-1]) + 1 + len(t) <= width:
            lines[-1] += " " + t
        else:
            lines.append(t)
    return lines


def _wrap(text: str, width: int, max_lines: int) -> str:
    """Split into ≤ max_lines lines of ≤ width chars; two lines are balanced when possible."""
    if len(text) <= width or max_lines < 2:
        return text
    tokens = text.split(" ")
    best = None
    for i in range(1, len(tokens)):
        a, b = " ".join(tokens[:i]), " ".join(tokens[i:])
        if len(a) <= width and len(b) <= width and (best is None or max(len(a), len(b)) < best[0]):
            best = (max(len(a), len(b)), a, b)
    if best:
        return f"{best[1]}\n{best[2]}"
    return "\n".join(_greedy_lines(tokens, width))


def build_cues(segments: list[dict], cfg: SubtitleConfig) -> list[Cue]:
    def fits(toks: list[tuple[str, float, float]]) -> bool:
        return len(_greedy_lines([t for t, _, _ in toks], cfg.max_line_chars)) <= cfg.max_lines

    def emit(toks: list[tuple[str, float, float]]) -> None:
        cues.append(Cue(toks[0][1], toks[-1][2], " ".join(t for t, _, _ in toks)))

    cues: list[Cue] = []
    for seg in segments:
        cur: list[tuple[str, float, float]] = []
        for tok in timed_tokens(seg):
            if cur and (not fits(cur + [tok]) or tok[2] - cur[0][1] > cfg.max_cue_s):
                emit(cur)
                cur = []
            cur.append(tok)
            # break after a sentence end once the cue is reasonably full
            if tok[0][-1] in ".?!" and len(" ".join(t for t, _, _ in cur)) > cfg.max_line_chars:
                emit(cur)
                cur = []
        if cur:
            emit(cur)
    # minimum duration, no overlaps
    for i, cue in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else float("inf")
        if cue.end - cue.start < cfg.min_cue_s:
            cue.end = cue.start + cfg.min_cue_s
        cue.end = max(cue.start + 0.05, min(cue.end, nxt))
        cue.text = _wrap(cue.text, cfg.max_line_chars, cfg.max_lines)
    return cues


def _ts(seconds: float, sep: str) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    return "\n".join(f"{i}\n{_ts(c.start, ',')} --> {_ts(c.end, ',')}\n{c.text}\n" for i, c in enumerate(cues, 1))


def to_vtt(cues: list[Cue]) -> str:
    return "WEBVTT\n\n" + "\n".join(f"{_ts(c.start, '.')} --> {_ts(c.end, '.')}\n{c.text}\n" for c in cues)
