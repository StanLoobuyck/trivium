"""Guesses from a recording's file name: title, date, course; and which files are recordings or slides."""

from __future__ import annotations

import re
from datetime import datetime

VIDEO_EXT = {".mp4", ".mkv", ".mov", ".webm", ".m4a", ".mp3", ".wav", ".flac", ".ogg", ".opus", ".aac", ".m4v", ".ts"}
SLIDE_EXT = {".pdf", ".pptx"}
MONTHS = {m: i for i, m in enumerate(
    ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
     "november", "december"], start=1)}
MONTHS |= {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
def guess_title(stem: str) -> str:
    """'DEP Les 3, part 1 - …' → 'Les 3 deel 1'; 'Lecture 5' → 'Lecture 5'; else the cleaned file name."""
    m = re.search(r"\b(les|lecture|college|hoorcollege|week)\s*(\d+)", stem, re.I)
    if not m:
        return re.sub(r"[_]+", " ", stem).strip()[:60]
    word = m.group(1).lower()
    title = f"{'Les' if word in ('les', 'college', 'hoorcollege') else word.capitalize()} {m.group(2)}"
    part = re.search(r"\b(part|deel)\s*(\d+)", stem[m.end():], re.I)
    return title + (f" deel {part.group(2)}" if part else "")


def guess_date(stem: str, mtime: float) -> str:
    if m := re.search(r"(20\d\d)-(\d\d)-(\d\d)", stem):
        return m.group(0)
    if m := re.search(r"(\d{1,2})(?:ste|de|e|st|nd|rd|th)?\s+(\w+)\s+(20\d\d)|(\w+)\s+(\d{1,2})(?:ste|de|e|st|nd|rd|th)?,?\s+(20\d\d)",
                      stem, re.I):
        day, month, year = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(5), m.group(4), m.group(6))
        if month.lower() in MONTHS:
            return f"{year}-{MONTHS[month.lower()]:02d}-{int(day):02d}"
    return datetime.fromtimestamp(mtime).date().isoformat()


def guess_course(stem: str, courses) -> str | None:
    words = set(re.findall(r"\w+", stem.lower()))
    best, score = None, 0
    for c in courses:
        cw = {w for w in re.findall(r"\w+", c.name.lower()) if len(w) > 3}
        hit = len(cw & words)
        if hit > score:
            best, score = c.id, hit
    return best if score >= 2 else None
