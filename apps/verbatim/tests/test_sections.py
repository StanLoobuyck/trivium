"""Stage 6: slide ↔ transcript alignment and the no-slides fallback."""

import pytest

from lecture.config import load_config
from lecture.stages import s6_sections

TOPICS = [
    ("De Morgan", "regel van de morgan inverteren nand nor doorduwen invertoren"),
    ("Multiplexer", "multiplexer selectiebit ingang doorlaten mux kiezen"),
    ("Decoder", "decoder enable uitgangen cascaderen adres"),
    ("Ripple carry adder", "ripple carry adder optellen full adder overdracht"),
]


@pytest.fixture
def conf(xdg):
    return load_config()


def _slides():
    return [{"file": "s.pdf", "page": 10 + i, "group": i, "title": t, "text": txt, "notes": "", "section": "Les 4"}
            for i, (t, txt) in enumerate(TOPICS)]


def _segments(plan):
    """plan: [(topic index, minutes)], one 10 s segment per step, lecturer speech about that topic."""
    segs, t = [], 0.0
    for topic, minutes in plan:
        for k in range(int(minutes * 6)):
            words = TOPICS[topic][1].split()
            text = f"en dan zien we hier {words[k % len(words)]} en {words[(k + 2) % len(words)]} zoals je ziet"
            segs.append({"start": t, "end": t + 9.0, "text": text})
            t += 10.0
    return segs


def test_alignment_follows_the_lecture_and_reports_skipped_slides(conf):
    segs = _segments([(0, 4), (1, 5), (3, 3)])  # decoder slide skipped
    result = s6_sections.run(segs, _slides(), "nl", conf)
    secs = result["sections"]
    assert [s["title"] for s in secs] == ["De Morgan", "Multiplexer", "Ripple carry adder"]
    assert secs[1]["start"] == pytest.approx(240, abs=conf.sections.window_s)
    assert secs[2]["start"] == pytest.approx(540, abs=conf.sections.window_s)
    assert [s["page"] for s in result["slides_not_discussed"]] == [12]
    assert secs[0]["slides"] == [{"file": "s.pdf", "page": 10}] and not secs[0]["low_confidence"]


def test_short_mention_of_an_earlier_slide_does_not_jump_back(conf):
    # 30 s about De Morgan in the middle of the multiplexer part: going back costs more than one window
    segs = _segments([(0, 3), (1, 3), (0, 0.5), (1, 3)])
    titles = [s["title"] for s in s6_sections.run(segs, _slides(), "nl", conf)["sections"]]
    assert titles == ["De Morgan", "Multiplexer"]


def test_no_slides_sections_cut_at_longest_pause(conf):
    segs = [{"start": i * 10.0, "end": i * 10.0 + 9.0, "text": "tekst"} for i in range(150)]  # 25 min
    segs[40]["end"] = segs[40]["start"] + 2.0  # an 8 s pause before 410 s: inside the 5–8 min range
    result = s6_sections.run(segs, [], "nl", conf)
    starts = [s["start"] for s in result["sections"]]
    assert result["method"] == "pauses" and starts[:2] == [0.0, 410.0]
    assert all(b - a <= conf.sections.no_slides_max_s for a, b in zip(starts, starts[1:]))
    assert result["sections"][-1]["end"] == segs[-1]["end"]


def test_markdown_every_segment_once_with_headings(conf):
    segs = _segments([(0, 2), (1, 2)])
    slides = _slides()
    result = s6_sections.run(segs, slides, "nl", conf)
    md = s6_sections.render_markdown(result, segs, "Les 4 — DEP", "nl", many_files=False)
    assert md.startswith("# Les 4 — DEP")
    assert "## 1. De Morgan (slide 10) · 00:00:00–" in md and "## 2. Multiplexer (slide 11)" in md
    assert sum(line.startswith("[") for line in md.splitlines()) == len(segs)
