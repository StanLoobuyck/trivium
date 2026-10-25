"""Stage 6: transcript sections per slide group (text alignment), or every few minutes without slides.

Slide groups (text + notes) and ~30 s transcript windows are compared with character n-gram TF-IDF (robust
to misspelled terms: "nend" still shares n-grams with "NAND"). A dynamic programme then picks one group
per window: staying or moving to the next slide is cheap, skipping ahead costs more the further it goes,
going back costs most. Writes `sections.json` and `outputs/transcript.md`.
"""

from __future__ import annotations

import numpy as np

from ..config import Config, SectionsConfig
from ..textnorm import normalize_text
from ..util import fmt_ts

_UNCERTAIN = {"nl": "slide onzeker", "en": "slide uncertain"}
_SLIDE = {"nl": "slide", "en": "slide"}
_PART = {"nl": "Deel", "en": "Part"}


def windows(segments: list[dict], window_s: float) -> list[list[dict]]:
    """Consecutive segments grouped into windows of about window_s (never splits a segment)."""
    out: list[list[dict]] = []
    for seg in segments:
        if out and seg["start"] - out[-1][0]["start"] < window_s:
            out[-1].append(seg)
        else:
            out.append([seg])
    return out


def similarity(group_texts: list[str], window_texts: list[str]) -> np.ndarray:
    """windows × groups similarity, scaled so each window's best group is 1.

    Each group's median similarity over the lecture is subtracted first: an overview slide ("In deze
    les…") resembles every window a little and would otherwise win wherever nothing matches strongly.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    vec.fit(group_texts + window_texts)
    sim = (vec.transform(window_texts) @ vec.transform(group_texts).T).toarray()
    sim = np.clip(sim - np.median(sim, axis=0, keepdims=True), 0.0, None)
    return sim / np.maximum(sim.max(axis=1, keepdims=True), 1e-9)


def transition_costs(n: int, cfg: SectionsConfig) -> np.ndarray:
    k = np.arange(n)[None, :] - np.arange(n)[:, None]  # slides moved forward (negative = back)
    cost = np.where(k == 1, cfg.next_cost, 0.0)
    cost = np.where(k > 1, cfg.next_cost + cfg.skip_cost * np.abs(k - 1) ** 0.7, cost)
    return np.where(k < 0, cfg.back_cost + 0.1 * np.abs(k) ** 0.7, cost)


def best_path(sim: np.ndarray, cfg: SectionsConfig) -> list[int]:
    """Viterbi over groups: minimises Σ (1 - similarity) + transition costs."""
    t_count, n = sim.shape
    trans = transition_costs(n, cfg)
    cost = (1 - sim[0]) + cfg.skip_cost * 0.5 * np.arange(n)  # a lecture usually starts at its first slides
    back = np.zeros((t_count, n), dtype=int)
    for t in range(1, t_count):
        total = cost[:, None] + trans
        back[t] = total.argmin(axis=0)
        cost = total.min(axis=0) + (1 - sim[t])
    path = [int(cost.argmin())]
    for t in range(t_count - 1, 0, -1):
        path.append(int(back[t][path[-1]]))
    return path[::-1]


def align(segments: list[dict], slides: list[dict], language: str, cfg: SectionsConfig) -> dict:
    groups: dict[int, list[dict]] = {}
    for s in slides:
        groups.setdefault(s["group"], []).append(s)
    gids = list(groups)
    gtext = [normalize_text(" ".join(f"{s['title'] or ''} {s['text']} {s['notes']}" for s in groups[g]), language)
             for g in gids]
    wins = windows(segments, cfg.window_s)
    sim = similarity(gtext, [normalize_text(" ".join(s["text"] for s in w), language) for w in wins])
    path = best_path(sim, cfg)
    sections: list[dict] = []
    for t, g in enumerate(path):
        second = np.sort(sim[t])[-2] if sim.shape[1] > 1 else 0.0
        margin = float(1.0 - second) if sim[t, g] >= 1.0 else 0.0  # 0 when the path overrules this window
        if sections and sections[-1]["_g"] == g:
            sections[-1]["end"] = wins[t][-1]["end"]
            sections[-1]["_margins"].append(margin)
            continue
        first = groups[gids[g]][0]
        sections.append({"_g": g, "group": gids[g], "title": first["title"],
                         "slides": [{"file": s["file"], "page": s["page"]} for s in groups[gids[g]]],
                         "start": wins[t][0]["start"], "end": wins[t][-1]["end"], "_margins": [margin]})
    for i, s in enumerate(sections):
        s["index"] = i + 1
        s["confidence"] = round(float(np.mean(s.pop("_margins"))), 3)
        s["low_confidence"] = s["confidence"] < cfg.low_confidence
        del s["_g"]
    visited = {s["group"] for s in sections}
    return {"method": "slides", "sections": sections,
            "slides_not_discussed": [{"file": s["file"], "page": s["page"], "title": s["title"]}
                                     for s in slides if s["group"] not in visited]}


def by_pauses(segments: list[dict], cfg: SectionsConfig) -> dict:
    """No slides: a section every min_s–max_s, cut at the longest pause in that range."""
    sections: list[dict] = []
    start_i = 0
    while start_i < len(segments):
        t0 = segments[start_i]["start"]
        candidates = [i for i in range(start_i + 1, len(segments))
                      if cfg.no_slides_min_s <= segments[i]["start"] - t0 <= cfg.no_slides_max_s]
        if not candidates or segments[-1]["end"] - t0 <= cfg.no_slides_max_s:
            cut = len(segments)
        else:
            cut = max(candidates, key=lambda i: segments[i]["start"] - segments[i - 1]["end"])
        sections.append({"index": len(sections) + 1, "group": None, "title": None, "slides": [],
                         "start": segments[start_i]["start"], "end": segments[cut - 1]["end"],
                         "confidence": None, "low_confidence": False})
        start_i = cut
    return {"method": "pauses", "sections": sections, "slides_not_discussed": []}


def render_markdown(result: dict, segments: list[dict], heading: str, language: str, many_files: bool) -> str:
    lines = [f"# {heading}", ""]
    for sec in result["sections"]:
        if result["method"] == "slides":
            pages = sorted({s["page"] for s in sec["slides"]})
            where = f"{_SLIDE[language]} {pages[0]}" + (f"–{pages[-1]}" if len(pages) > 1 else "")
            if many_files:
                where += f", {sec['slides'][0]['file']}"
            title = f"{sec['index']}. {sec['title'] or '…'} ({where})"
            if sec["low_confidence"]:
                title += f" ({_UNCERTAIN[language]})"
        else:
            title = f"{_PART[language]} {sec['index']}"
        lines += [f"## {title} · {fmt_ts(sec['start'])}–{fmt_ts(sec['end'])}", ""]
        # section boundaries are segment starts, so every segment lands in exactly one section
        lines += [f"[{fmt_ts(s['start'])}] {s['text'].strip()}" for s in segments
                  if sec["start"] <= s["start"] < sec["end"]]
        lines.append("")
    return "\n".join(lines)


def run(segments: list[dict], slides: list[dict], language: str, conf: Config) -> dict:
    if not segments:
        return {"method": "none", "sections": [], "slides_not_discussed": []}
    if not slides:
        return by_pauses(segments, conf.sections)
    return align(segments, slides, language, conf.sections)
