"""How the library orders lectures: lesson and part from the title, a cleaner title for raw file names, the order
within a course and which parts belong together. All derived for display; nothing here is written to a manifest.

Lesson numbers for raw file names ("ABC - Aula 1 2026-10-13 10 - 53") come from Sequo through the hub
(the n-th lecture of the course in the timetable, counted like Sequo). Without a hub the title falls back to the date.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import date as Date
from datetime import datetime
from pathlib import Path

from .naming import guess_title
from .semesters import semester_of

_LESSON = re.compile(r"\b(?:les|lecture|college|hoorcollege|week)\s*0*(\d+)", re.I)
_PART = re.compile(r"\b(?:deel|part)\s*0*(\d+)", re.I)
_MONTHS = {"nl": "jan feb mrt apr mei jun jul aug sep okt nov dec".split(),
           "en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()}
REFRESH_S = 600  # ask the hub again after 10 minutes; the cached answer is used meanwhile (and when offline)


def parse_lesson(title: str) -> tuple[int | None, int | None]:
    """'Les 11 deel 3' → (11, 3); 'Lecture 5' → (5, None); 'Les van 13 okt' → (None, None)."""
    m = _LESSON.search(title)
    if not m:
        return None, None
    p = _PART.search(title[m.end():])
    return int(m[1]), int(p[1]) if p else None


def date_title(day: str, lang: str) -> str:
    d = Date.fromisoformat(day[:10])
    month = _MONTHS["en" if lang == "en" else "nl"][d.month - 1]
    return f"Lecture of {d.day} {month}" if lang == "en" else f"Les van {d.day} {month}"


def display_title(title: str, stem: str | None, day: str | None, lessons: list[dict], lang: str = "nl") -> str:
    """The title the library shows. A title with a lesson number, or one renamed by hand, stays (spaces tidied).
    A title still equal to the guess from the file name gets 'Les n' from the timetable, else the date."""
    clean = " ".join(title.split())
    if parse_lesson(clean)[0] is not None or not stem or clean != " ".join(guess_title(stem).split()):
        return clean
    numbers = {x["number"] for x in lessons if x.get("date") == day}
    if len(numbers) == 1:
        return f"{'Lecture' if lang == 'en' else 'Les'} {numbers.pop()}"
    return date_title(day, lang) if day else clean


def arrange(lectures: list[dict]) -> None:
    """Adds lesson, part, semester, rank (order within the course, 0 = first) and group (parts of one lesson share it).
    A lecture without a number sits after the numbered one held on or before its date."""
    for x in lectures:
        x["lesson"], x["part"] = parse_lesson(x["title"])
        x["semester"] = semester_of(x["date"]) if x.get("date") else ""
        x["group"] = f"{x['course']}|{x['semester']}|{x['lesson']}" if x["lesson"] is not None and x["part"] else None
    by_course: dict[str, list[dict]] = {}
    for x in lectures:
        by_course.setdefault(x["course"], []).append(x)
    for own in by_course.values():
        def eff(x: dict) -> float:
            if x["lesson"] is not None:
                return x["lesson"]
            before = [y["lesson"] for y in own if y["lesson"] is not None and y["semester"] == x["semester"]
                      and (y.get("date") or "") <= (x.get("date") or "")]
            return max(before, default=0) + 0.5
        keyed = sorted(own, key=lambda x: (x["semester"], eff(x), x["part"] or 0, x.get("date") or "", x["title"]))
        for i, x in enumerate(keyed):
            x["rank"] = i


# --- lesson numbers from the hub, cached next to the jobs ------------------------------------------------------

_lock = threading.Lock()
_busy = False


def _match(entry: dict, courses: list) -> str | None:
    """Same rule as hub.course_colors: same timetable code, else same name."""
    def key(name: str) -> str:
        return " ".join(name.lower().split())
    wanted = {c.upper() for c in entry.get("codes") or []}
    same = next((c for c in courses if wanted & {x.upper() for x in c.codes}), None) \
        or next((c for c in courses if key(c.name) == key(entry.get("name") or "")), None)
    return same.id if same else None


def lessons_from_hub(entries: list[dict], courses: list) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for entry in entries:
        if (cid := _match(entry, courses)) and entry.get("lectures"):
            out.setdefault(cid, []).extend(entry["lectures"])
    return out


def cached_lessons(cache: Path, refresh) -> dict[str, list[dict]]:
    """What the hub last said ({course id: [{date, number}]}). Older than REFRESH_S: refresh() runs in the
    background (never blocking the page); a failed refresh keeps the old answer."""
    from .util import read_json, write_json

    global _busy
    data = read_json(cache) if cache.exists() else {}
    if time.time() - data.get("at", 0) > REFRESH_S:
        with _lock:
            start, _busy = not _busy, True
        if start:
            def run() -> None:
                global _busy
                try:
                    lessons = refresh()
                    if lessons is not None:
                        write_json(cache, {"at": time.time(), "fetched": datetime.now().isoformat(timespec="seconds"),
                                           "lessons": lessons})
                except Exception:  # noqa: BLE001 - offline or no hub: keep what we had
                    pass
                finally:
                    _busy = False
            threading.Thread(target=run, daemon=True).start()
    return data.get("lessons", {})
