"""Stage 2: slide text (PDF/PPTX) per slide, overlay groups, the lecture's slide selection and term list.

Writes `slides/slides.json` (all slides, for alignment in Stage 6) and `terms.json` (term list + Whisper
prompt). A multi-lecture PDF ("Deel 2 (Les 3-6)") is narrowed to the outline section matching the job
title ("Les 4") for the term list; slides.json keeps every slide with its section.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from ..config import Config, Course
from ..job import Job
from ..report import Reporter
from ..terms import build_term_list, build_whisper_prompt
from ..util import hash_data, write_json

_SLIDE_TITLE = re.compile(r"^Slide \d+:?\s*")  # PowerPoint-exported PDF outlines: "Slide 12: Full adder"


def extract_pdf(path: Path) -> list[dict]:
    import pymupdf

    doc = pymupdf.open(path)
    toc = doc.get_toc()
    titles = {page: _SLIDE_TITLE.sub("", title).strip() for _, title, page in toc if _SLIDE_TITLE.match(title)}
    # level-1 outline entries are sections ("Les 4"), except a PowerPoint export's "Slide N: …" entries
    sections = sorted((page, title.strip()) for level, title, page in toc
                      if level == 1 and not _SLIDE_TITLE.match(title))
    slides = []
    for i, page in enumerate(doc, start=1):
        lines = [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]
        section = None
        for start, title in sections:
            if start <= i:
                section = title
        slides.append({"page": i, "section": section, "title": titles.get(i) or _largest_span(page),
                       "lines": lines, "notes": ""})
    return slides


def _largest_span(page) -> str | None:
    """Title guess: the text in the largest font on the page."""
    best, size = None, 0.0
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["text"].strip() and span["size"] > size + 0.5:
                    best, size = span["text"].strip(), span["size"]
    return best


def extract_pptx(path: Path) -> list[dict]:
    from pptx import Presentation

    slides = []
    for i, slide in enumerate(Presentation(str(path)).slides, start=1):
        lines, title = [], None
        for shape in _all_shapes(slide.shapes):
            if shape.has_text_frame:
                text = [p.text.strip() for p in shape.text_frame.paragraphs if p.text.strip()]
                if shape.is_placeholder and shape.placeholder_format.type in (1, 3) and text:  # TITLE, CENTER_TITLE
                    title = " ".join(text)
                lines += text
            elif shape.has_table:
                lines += [c.text.strip() for row in shape.table.rows for c in row.cells if c.text.strip()]
        notes = ""
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        slides.append({"page": i, "section": None, "title": title, "lines": lines, "notes": notes})
    return slides


def _all_shapes(shapes):
    """Shapes including those inside groups (grouped text boxes are common on diagrams)."""
    for shape in shapes:
        if shape.shape_type == 6:  # MSO_SHAPE_TYPE.GROUP
            yield from _all_shapes(shape.shapes)
        else:
            yield shape


def strip_boilerplate(slides: list[dict], conf: Config) -> dict[str, list[str]]:
    """Remove lines repeated on most slides of a section (sidebar, footer). Returns removed lines per section."""
    removed: dict[str, list[str]] = {}
    by_section: dict[str | None, list[dict]] = {}
    for s in slides:
        by_section.setdefault(s["section"], []).append(s)
    for section, group in by_section.items():
        if len(group) < conf.slides.boilerplate_min_pages:
            continue
        counts = Counter(ln for s in group for ln in set(s["lines"]))
        common = {ln for ln, n in counts.items() if n >= conf.slides.boilerplate_fraction * len(group)}
        for s in group:
            s["lines"] = [ln for ln in s["lines"] if ln not in common]
        removed[section or ""] = sorted(common)
    return removed


def group_overlays(slides: list[dict]) -> None:
    """Consecutive slides of one file get the same group id when the text of the first is contained in the
    next (beamer \\pause) or both have the same title (PowerPoint build-ups: "Eenvoudige ALU …" ×3)."""
    group = 0
    for i, s in enumerate(slides):
        if i > 0:
            prev = slides[i - 1]
            overlay = prev["lines"] and set(prev["lines"]) <= set(s["lines"])
            same_title = bool(prev["title"]) and prev["title"] == s["title"]
            if not (prev["file"] == s["file"] and (overlay or same_title)):
                group += 1
        s["group"] = group


def select_for_lecture(slides: list[dict], title: str) -> tuple[str | None, list[dict]]:
    """The outline section named in the job title ("Les 4" in "Les 4", "Les 3" in "Les 3 deel 1")."""
    for section in dict.fromkeys(s["section"] for s in slides if s["section"]):
        if re.search(rf"(?<!\w){re.escape(section.lower())}(?!\w)", title.lower()):
            return section, [s for s in slides if s["section"] == section]
    return None, slides


def input_hash(job: Job, course: Course, conf: Config) -> str:
    return hash_data({"slides": [s["fingerprint"] for s in job.slides], "title": job.manifest.get("title"),
                      "course": course.model_dump(), "slides_cfg": conf.slides.model_dump(),
                      "terms_cfg": conf.terms.model_dump(), "version": 2})


def run(job: Job, course: Course, conf: Config, rep: Reporter) -> dict:
    """Extract all slide files of the job; write slides.json and terms.json. Returns terms.json content."""
    slides: list[dict] = []
    boilerplate: dict[str, list[str]] = {}
    for entry in job.slides:
        path = job.slides_dir / entry["file"]
        extracted = extract_pdf(path) if path.suffix.lower() == ".pdf" else extract_pptx(path)
        for s in extracted:
            s["file"] = entry["file"]
        for section, lines in strip_boilerplate(extracted, conf).items():
            boilerplate[section] = sorted({*boilerplate.get(section, []), *lines})
        slides += extracted
    group_overlays(slides)
    for i, s in enumerate(slides):
        s["id"] = i
        s["text"] = "\n".join(s.pop("lines"))
    section, selected = select_for_lecture(slides, job.manifest.get("title") or "")
    write_json(job.slides_dir / "slides.json", {"slides": slides, "boilerplate": boilerplate,
                                                 "lecture_section": section})
    sidebar = boilerplate.get(section or "", [])  # the lecture's sidebar terms (Karnaugh, MUX), counted once
    terms = build_term_list([f"{s['title'] or ''}\n{s['text']}\n{s['notes']}" for s in selected],
                            sidebar, course, conf)
    prompt = build_whisper_prompt(terms, course, conf.terms.prompt_max_tokens)
    result = {"lecture_section": section, "slides_used": len(selected), "terms": terms, "whisper_prompt": prompt}
    write_json(job.root / "terms.json", result)
    if job.slides:
        groups = len({s["group"] for s in slides})
        rep.info(f"Slides: {len(slides)} pages in {groups} groups"
                 + (f"; this lecture: {section} ({len(selected)} pages)" if section else "")
                 + f"; {len(terms)} terms")
    return result
