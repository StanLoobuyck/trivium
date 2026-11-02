# /// script
# requires-python = ">=3.11"
# ///
"""Checks a finished lecture file against its parts.md: what a model reports about itself is not proof.

  uv run check.py <lecture.tex> <WORK folder> [--pages N]

Prints one line per problem and exits 1 when there are any. N = this lecture's pages in the PDF.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PAGES_PER_HOUR = 5
MARGIN = 1.2
MIN_BUDGET = 3  # a short recording still needs its figures and code: 2 pages made Opus drop circuits
PART = re.compile(r"^## Part \d+: .*\[([\d:]+)–([\d:]+)\] · slides (.*?)(?: \(slide match uncertain\))?$", re.M)
STAMP = re.compile(r"^\[([\d:]+)\]", re.M)
SLIDE = re.compile(r"\\slide\{([^}]*)\}\{([^}]*)\}")


def seconds(text: str) -> int:
    value = 0
    for field in text.split(":"):
        value = value * 60 + int(field)
    return value


def page_of(label: str) -> str:
    return re.sub(r"\s+", " ", label).strip().removeprefix("p")


def check(tex: str, parts: str, pages: int | None) -> list[str]:
    problems = []
    body = "\n".join(line for line in tex.splitlines() if not line.lstrip().startswith("%"))
    stamps = [seconds(s) for s in STAMP.findall(parts)]
    end = max(stamps, default=0)
    known = [(seconds(a), seconds(b), {page_of(x) for x in c.split(", ")}, "uncertain" in line)
             for line in (m[0] for m in PART.finditer(parts))
             for a, b, c in [PART.match(line).groups()]]
    last = -1
    for page, moment in SLIDE.findall(body):
        if not moment:
            continue
        if not re.fullmatch(r"\d+(:\d\d)+", moment):
            problems.append(f"\\slide{{{page}}}{{{moment}}}: second argument must be a time or empty")
            continue
        at = seconds(moment)
        if at > end:
            problems.append(f"\\slide{{{page}}}{{{moment}}}: after the end of the recording ({end // 60}:{end % 60:02d})")
        if at < last:
            problems.append(f"\\slide{{{page}}}{{{moment}}}: goes back in time; a moment must be when it was really said")
        last = max(last, at)
        around = [p for p in known if p[0] <= at <= p[1]]  # a moment on the border belongs to both parts
        if around and not any(p[3] or page_of(page) in p[2] for p in around):
            problems.append(f"\\slide{{{page}}}{{{moment}}}: parts.md has slides {sorted(around[0][2])} at that moment")
    if "Verbatim: being written" in tex or not re.search(r"\\les\{", body):
        problems.append("the lecture file isn't written: no \\les")
    if re.search(r"\\providecommand|\\newcommand|\\setlength", body):
        problems.append("own macros or lengths in the lecture file: use lesnotities.sty")
    if pages is not None:
        budget = max(MIN_BUDGET, end / 3600 * PAGES_PER_HOUR)
        print(f"{pages} pages, budget {budget:.1f}")
        if pages > budget * MARGIN:
            problems.append(f"{pages} pages is over the budget of {budget:.1f}: compress")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tex", type=Path)
    ap.add_argument("work", type=Path)
    ap.add_argument("--pages", type=int)
    a = ap.parse_args()
    problems = check(a.tex.read_text(encoding="utf-8"), (a.work / "parts.md").read_text(encoding="utf-8"), a.pages)
    for problem in problems:
        print(problem)
    print(f"check: {len(re.findall('% CHECK', a.tex.read_text(encoding='utf-8')))} % CHECK lines, {len(problems)} problems")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
