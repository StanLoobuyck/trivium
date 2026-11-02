# /// script
# requires-python = ">=3.11"
# dependencies = ["pymupdf>=1.24", "python-pptx>=1.0"]
# ///
"""Collect a lecture's material for the latex-notes skill into one work folder.

Input, either:
  a Verbatim job folder (~/Lectures/jobs/<lecture>): transcript already split into parts and
  matched to slide pages, or
  loose files: a transcript (.txt / .srt / .vtt / .md) plus slides (.pdf / .pptx).

Output in --out:
  lecture.json   course, title, date, language, lecturer, slide files
  parts.md       per part: time range, slide pages, slide text, transcript with [mm:ss] stamps
  slides/pNNN.png  low-res previews of the lecture's PDF pages (to spot figures); PPTX: embedded pictures
                   with several decks the name starts with the deck: d2_pNNN.png, and parts.md says "d2 p56"

Usage:
  uv run prepare.py --job ~/Lectures/jobs/2026-03-05_digitale-elektronica_les-6 --out WORK
  uv run prepare.py --transcript les.srt --slides les.pdf [--slides more.pptx] --out WORK
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PREVIEW_DPI = 60
PARA_S = 45  # transcript paragraphs of ~45 s, each with one timestamp


def ts(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def paragraphs(segments: list[dict]) -> list[str]:
    """[mm:ss] text … in blocks of about PARA_S seconds."""
    out, cur, start = [], [], None
    for s in segments:
        if start is None:
            start = s["start"]
        cur.append(s["text"].strip())
        if s["end"] - start >= PARA_S:
            out.append(f"[{ts(start)}] " + " ".join(cur))
            cur, start = [], None
    if cur:
        out.append(f"[{ts(start)}] " + " ".join(cur))
    return out


def render_previews(pdf: Path, pages: list[int], out: Path, tag: str = "") -> dict[int, list[float]]:
    """PNG previews of the given 1-based pages; returns page size in pt (for crop.py)."""
    import pymupdf as fitz

    sizes = {}
    doc = fitz.open(pdf)
    out.mkdir(parents=True, exist_ok=True)
    for p in pages:
        if 1 <= p <= doc.page_count:
            page = doc[p - 1]
            page.get_pixmap(dpi=PREVIEW_DPI).save(out / f"{tag}p{p:03d}.png")
            sizes[p] = [round(page.rect.width, 1), round(page.rect.height, 1)]
    return sizes


def pdf_texts(pdf: Path) -> list[str]:
    import pymupdf as fitz

    return [page.get_text().strip() for page in fitz.open(pdf)]


def pptx_texts_and_pictures(pptx: Path, out: Path, pages: set[int] | None = None) -> list[str]:
    """Text per slide; embedded pictures saved as slides/<stem>_sNNN_k.<ext> (only of `pages` when given).
    The name has no spaces or brackets: it ends up in an \\includegraphics."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    texts = []
    out.mkdir(parents=True, exist_ok=True)
    for i, slide in enumerate(Presentation(pptx).slides, start=1):
        lines, k = [], 0
        for shape in slide.shapes:
            if shape.has_text_frame:
                lines += [p.text for p in shape.text_frame.paragraphs if p.text.strip()]
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE and (pages is None or i in pages):
                k += 1
                img = shape.image
                stem = re.sub(r"[^\w-]+", "_", pptx.stem, flags=re.ASCII)
                (out / f"{stem}_s{i:03d}_{k}.{img.ext}").write_bytes(img.blob)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
            lines.append("[speaker notes] " + slide.notes_slide.notes_text_frame.text.strip())
        texts.append("\n".join(lines))
    return texts


def from_job(job: Path, out: Path) -> None:
    m = json.loads((job / "manifest.json").read_text())
    sections = json.loads((job / "sections.json").read_text())
    segments = json.loads((job / "transcript_raw.json").read_text())["segments"]
    slides = json.loads((job / "slides" / "slides.json").read_text()) if (job / "slides" / "slides.json").exists() else {}
    text_of = {(s["file"], s["page"]): s["text"] for s in slides.get("slides", [])}
    terms = json.loads((job / "terms.json").read_text()) if (job / "terms.json").exists() else {}
    lecturer = next((t["term"] for t in terms.get("terms", []) if t.get("source") == "lecturer"), None)

    decks = [s["file"] for s in m.get("slides", [])]
    tag = {f: f"d{i}_" if len(decks) > 1 else "" for i, f in enumerate(decks, start=1)}
    label = lambda f, p: f"{tag.get(f, '').rstrip('_')} p{p}".strip()

    used: dict[str, set[int]] = {}
    lines = [f"# {m.get('title')} ({m.get('date')}), course {m['course']}, spoken language {m['language']}", ""]
    if len(decks) > 1:
        lines += ["Decks: " + "; ".join(f"{tag[f].rstrip('_')} = {f}" for f in decks), ""]
    for sec in sections["sections"]:
        pages = [(s["file"], s["page"]) for s in sec.get("slides", [])]
        for f, p in pages:
            used.setdefault(f, set()).add(p)
        where = ", ".join(label(f, p) for f, p in pages) or "no slide"
        flag = " (slide match uncertain)" if sec.get("low_confidence") else ""
        lines += [f"## Part {sec['index']}: {sec['title']}  [{ts(sec['start'])}–{ts(sec['end'])}] · slides {where}{flag}", ""]
        for f, p in pages:
            lines += [f"### Slide {label(f, p)} text", text_of.get((f, p), "").strip() or "(no text)", ""]
        seg = [s for s in segments if sec["start"] <= s["start"] < sec["end"]]
        lines += ["### Transcript", *paragraphs(seg), ""]

    # Not discussed: only pages between the lecture's first and last slide are part of it. A deck for the whole
    # course has hundreds of other pages that belong to other lectures.
    between, outside = [], 0
    spans = {f: (min(p), max(p)) for f, p in used.items()}
    for s in sections.get("slides_not_discussed", []):
        f, p = (s["file"], s["page"]) if isinstance(s, dict) else (None, s)
        if f in spans and spans[f][0] <= p <= spans[f][1]:
            between.append((f, p))
        else:
            outside += 1
    if between or outside:
        lines += ["## Slides of this lecture not discussed in class", ""]
        for f, p in between:
            used[f].add(p)
            lines += [f"### Slide {label(f, p)} text", text_of.get((f, p), "").strip() or "(no text)", ""]
        if outside:
            lines += [f"({outside} other pages of these decks belong to other lectures: left out.)", ""]

    sizes = {}
    for f, pages in used.items():
        deck = job / "slides" / f
        if deck.suffix.lower() == ".pdf" and deck.exists():
            sizes[f] = render_previews(deck, sorted(pages), out / "slides", tag=tag.get(f, ""))
        elif deck.exists():
            pptx_texts_and_pictures(deck, out / "slides", pages)
    sources = {s["file"]: s["source"] for s in m.get("slides", [])}
    (out / "parts.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "lecture.json").write_text(json.dumps({
        "mode": "job", "job": str(job), "course_id": m["course"], "title": m.get("title"), "date": m.get("date"),
        "language": m["language"], "lecturer": lecturer,
        "slides": [{"file": f, "path": str(job / "slides" / f), "original": sources.get(f), "tag": tag.get(f, ""),
                    "pages": sorted(p),
                    "page_size_pt": sizes.get(f, {})} for f, p in used.items()],
    }, indent=2, ensure_ascii=False), encoding="utf-8")


_SRT_TIME = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d+)\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d+)")


def read_transcript(path: Path) -> list[dict]:
    """Segments with start/end/text from .srt/.vtt, or '[mm:ss] text' lines, or plain text (no times)."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    segs = []
    if path.suffix.lower() in (".srt", ".vtt"):
        for block in re.split(r"\n\s*\n", raw):
            lines = block.splitlines()
            for i, line in enumerate(lines):
                m = _SRT_TIME.search(line)
                if m:  # the cue text is everything after the time line
                    g = [int(x) for x in m.groups()]
                    text = " ".join(x.strip() for x in lines[i + 1:] if x.strip())
                    segs.append({"start": g[0] * 3600 + g[1] * 60 + g[2], "end": g[4] * 3600 + g[5] * 60 + g[6],
                                 "text": re.sub(r"<[^>]+>", "", text)})
                    break
        return segs
    for line in raw.splitlines():
        m = re.match(r"\[(?:(\d+):)?(\d+):(\d\d)\]\s*(.*)", line)
        if m:
            t = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            segs.append({"start": t, "end": t + 5, "text": m.group(4)})
        elif line.strip():
            segs.append({"start": 0, "end": 0, "text": line.strip()})
    return segs


def from_files(transcript: Path, slide_files: list[Path], out: Path) -> None:
    segs = read_transcript(transcript)
    lines = [f"# {transcript.stem} (loose files: transcript not matched to slides; match them yourself)", ""]
    info = []
    for sf in slide_files:
        if sf.suffix.lower() == ".pdf":
            texts = pdf_texts(sf)
            sizes = render_previews(sf, list(range(1, len(texts) + 1)), out / "slides", tag=f"{sf.stem}_")
        else:
            texts = pptx_texts_and_pictures(sf, out / "slides")
            sizes = {}
        info.append({"file": sf.name, "path": str(sf), "pages": list(range(1, len(texts) + 1)), "page_size_pt": sizes})
        lines += [f"## Slides: {sf.name}", ""]
        for i, t in enumerate(texts, start=1):
            lines += [f"### {sf.stem} p{i}", t or "(no text)", ""]
    lines += ["## Transcript", *(paragraphs(segs) if any(s["end"] for s in segs) else [s["text"] for s in segs]), ""]
    (out / "parts.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "lecture.json").write_text(json.dumps({
        "mode": "files", "transcript": str(transcript), "title": None, "date": None, "language": None,
        "slides": info}, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", type=Path)
    ap.add_argument("--transcript", type=Path)
    ap.add_argument("--slides", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    if a.job:
        from_job(a.job.expanduser(), a.out)
    elif a.transcript:
        from_files(a.transcript.expanduser(), [s.expanduser() for s in a.slides], a.out)
    else:
        ap.error("give --job, or --transcript (+ --slides)")
    info = json.loads((a.out / "lecture.json").read_text())
    words = len((a.out / "parts.md").read_text().split())
    print(f"ok: {a.out}/parts.md ({words} words), previews in {a.out}/slides/, "
          f"{sum(len(s['pages']) for s in info['slides'])} slide pages")


if __name__ == "__main__":
    main()
