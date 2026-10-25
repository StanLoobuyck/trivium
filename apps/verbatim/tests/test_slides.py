"""Stage 2 (slide text, boilerplate, lecture section, overlays) and the term list / Whisper prompt."""

import pytest

from lecture import terms
from lecture.config import Course, load_config
from lecture.stages import s2_slides

DEP = Course(id="dep", name="Digitale elektronica", language="nl", lecturer="Ada Example",
             extra_terms=["minterm"], notes_language="nl")


@pytest.fixture
def conf(xdg):
    return load_config()


@pytest.mark.parametrize("word,is_term", [
    ("NAND", True), ("ALU", True), ("Karnaugh", True), ("Booleaanse", True), ("carry", True),  # real DEP terms
    ("74LS00", True),
    ("poort", False), ("geheugen", False), ("dus", False),                 # ordinary Dutch
    ("𝐴𝐵", False), ("ҧ𝐴𝐵𝐶𝑖𝑛", False), ("X’Y", False), ("XY", False), ("ABC", False),  # formulas / variables
    ("DUUR", False), ("HERHALING", False), ("FALSE", False),                # capitals for emphasis
    ("B-KUL-H01L1A", False), ("Les3", False), ("c0", False),               # codes, numbered words, variables
])
def test_classify_real_slide_words(conf, word, is_term):
    assert (terms.classify(word, "nl", conf.terms.rare_zipf) > 0) == is_term


def test_regular_dutch_words_rank_below_jargon(conf):
    assert terms.classify("implementeerbare", "nl", 3.0) < terms.classify("Karnaugh", "nl", 3.0)


def test_term_list_course_terms_first_and_fragments_joined(conf):
    slides = ["Karnaugh kaart\nNAND poort", "Karnaugh\nCombina-\ntorisch", "e-mail Ada.Example@esat.kuleuven.be"]
    result = terms.build_term_list(slides, ["• MUX"], DEP, conf)
    names = [t["term"] for t in result]
    assert names[:2] == ["minterm", "Ada Example"]
    assert names[2] == "Karnaugh"  # on 2 slides, rare
    assert "MUX" in names and "Combina" not in names
    assert names[-1] == "Combinatorisch"  # joined over the line break; regular Dutch → lowest weight
    assert not any("esat" in n.lower() or "kuleuven" in n.lower() for n in names)


def test_prompt_fits_budget_and_terms_survive_long_tail(conf):
    many = [{"term": f"Term{i}xq"} for i in range(200)]
    prompt = terms.build_whisper_prompt(many, DEP, 120)
    assert prompt.startswith("Dit is een les van Digitale elektronica over Term0xq") and prompt.endswith(".")
    assert terms.count_tokens(prompt) <= 120
    combined = terms.combine_prompt(prompt, " ".join(["woord"] * 400))
    assert combined.startswith(prompt)  # Whisper keeps the end of a long prompt: terms must not be cut
    assert terms.count_tokens(combined) <= terms.WHISPER_PROMPT_MAX_TOKENS
    assert terms.combine_prompt("", "vorige zin") == "vorige zin"


def _slide(i, lines, section=None, file="a.pdf"):
    return {"page": i, "section": section, "title": None, "lines": lines, "notes": "", "file": file}


def test_boilerplate_per_section_and_lecture_selection(conf):
    slides = ([_slide(i, ["DEP (26-27)", "• Karnaugh", f"inhoud {i}"], "Les 3") for i in range(5)]
              + [_slide(5 + i, ["DEP (26-27)", "– MUX", f"inhoud {i}"], "Les 4") for i in range(5)])
    removed = s2_slides.strip_boilerplate(slides, conf)
    assert removed["Les 3"] == ["DEP (26-27)", "• Karnaugh"] and "– MUX" in removed["Les 4"]
    assert slides[0]["lines"] == ["inhoud 0"]
    assert s2_slides.select_for_lecture(slides, "Les 3 deel 1")[0] == "Les 3"
    assert s2_slides.select_for_lecture(slides, "Les 4")[1] == slides[5:]
    assert s2_slides.select_for_lecture(slides, "Les 30")[0] is None  # no partial number match


def test_overlays_grouped_within_one_file():
    slides = [_slide(1, ["SOP"]), _slide(2, ["SOP", "stap 2"]), _slide(3, ["POS"]),
              _slide(1, ["POS", "x"], file="b.pdf")]
    slides.insert(3, {**_slide(3, ["POS", "andere tekst"]), "title": "POS"})
    slides[2]["title"] = "POS"  # same title, different text: a PowerPoint build-up
    s2_slides.group_overlays(slides)
    assert [s["group"] for s in slides] == [0, 0, 1, 1, 2]


def test_extract_pdf_with_powerpoint_outline(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    for text in ["Deel 2", "Les3: Booleaanse algebra", "Karnaugh"]:
        doc.new_page().insert_text((72, 72), text, fontsize=12)
    doc.set_toc([[1, "Default Section", 1], [2, "Slide 1: Deel 2", 1],
                 [1, "Les 3", 2], [2, "Slide 2: Booleaanse algebra", 2], [2, "Slide 3", 3]])
    path = tmp_path / "s.pdf"
    doc.save(path)
    pages = s2_slides.extract_pdf(path)
    assert [p["section"] for p in pages] == ["Default Section", "Les 3", "Les 3"]
    assert pages[1]["title"] == "Booleaanse algebra"
    assert pages[2]["title"] == "Karnaugh"  # "Slide 3" has no title: largest text on the page


def test_extract_pptx_title_groups_tables_and_notes(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
    slide.shapes.title.text = "HVDC verbindingen"
    group = slide.shapes.add_group_shape()
    group.shapes.add_textbox(Inches(1), Inches(2), Inches(3), Inches(1)).text_frame.text = "ALEGrO 1 GW"
    table = slide.shapes.add_table(1, 2, Inches(1), Inches(4), Inches(4), Inches(1)).table
    table.cell(0, 0).text, table.cell(0, 1).text = "XLPE", "kabel"
    slide.notes_slide.notes_text_frame.text = "Vertel over ENTSO-e"
    path = tmp_path / "s.pptx"
    prs.save(path)
    (page,) = s2_slides.extract_pptx(path)
    assert page["title"] == "HVDC verbindingen"
    assert {"ALEGrO 1 GW", "XLPE", "kabel"} <= set(page["lines"])  # text inside a group shape too
    assert page["notes"] == "Vertel over ENTSO-e"
