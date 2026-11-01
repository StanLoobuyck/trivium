"""Semesters (KU Leuven rhythm) and which courses are archived.

A semester is named "2026-27 S1": S1 = September–January (January's exams belong to it), S2 = February–August
(incl. the August resits). A course's semester is set in courses.yaml (`semester:`) or follows from its
newest lecture. Courses of past semesters are archived automatically; `archived: false` keeps one in the
current list ("Move back to current"), `archived: true` archives it early ("Archive this semester").
"""

from __future__ import annotations

import re
from datetime import date

from .config import Course

SEMESTER_RX = re.compile(r"^\d{4}-\d{2} S[12]$")


def semester_of(d: date | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if d.month >= 9:
        start, sem = d.year, 1
    elif d.month == 1:
        start, sem = d.year - 1, 1
    else:
        start, sem = d.year - 1, 2
    return f"{start}-{(start + 1) % 100:02d} S{sem}"


def current_semester(today: date | None = None) -> str:
    return semester_of(today or date.today())


def course_semester(course: Course, lecture_dates: list[str]) -> str:
    """The course's semester: set explicitly, else from its newest lecture, else the current one."""
    if course.semester:
        return course.semester
    dates = sorted(d for d in lecture_dates if d)
    return semester_of(dates[-1]) if dates else current_semester()


def is_archived(course: Course, semester: str, today: date | None = None) -> bool:
    if course.archived is not None:
        return course.archived
    return semester < current_semester(today)  # "2025-26 S2" < "2026-27 S1": names sort by time


def overview(courses: list[Course], lectures: list[dict], today: date | None = None) -> dict:
    """Per course: semester + archived; per semester: its courses. lectures: dicts with course and date."""
    by_course: dict[str, list[str]] = {}
    for lec in lectures:
        by_course.setdefault(lec.get("course"), []).append(lec.get("date") or "")
    out = {"current": current_semester(today), "courses": {}, "semesters": {}}
    for c in courses:
        sem = course_semester(c, by_course.get(c.id, []))
        archived = is_archived(c, sem, today)
        out["courses"][c.id] = {"semester": sem, "archived": archived, "explicit": c.archived is not None}
        out["semesters"].setdefault(sem, []).append(c.id)
    out["semesters"] = dict(sorted(out["semesters"].items(), reverse=True))
    return out
