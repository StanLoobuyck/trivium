"""Transcript fixes: course fix list and sound-alikes of slide terms (fixes.py)."""

from lecture.fixes import apply_fixes, skeleton

TERMS = [{"term": "Algebraïsche", "source": "slides"}, {"term": "NAND", "source": "slides"}, {"term": "NOR", "source": "slides"}, {"term": "VIL", "source": "slides"},
         {"term": "ALU", "source": "slides"}, {"term": "Booleaanse", "source": "slides"},
         {"term": "Ada Example", "source": "lecturer"}]


def seg(text):
    return {"text": text, "words": [{"word": w} for w in text.split()]}


def test_sound_alikes_of_slide_terms_are_fixed():
    assert skeleton("nent") == skeleton("NAND") == skeleton("nend")
    segs = [seg("een nent-poort en een NENT 3"), seg("de ELU rekent, boeliaanse algebra")]
    fixes = apply_fixes(segs, TERMS, {})
    assert segs[0]["text"] == "een NAND-poort en een NAND 3"
    assert segs[1]["text"] == "de ALU rekent, booleaanse algebra"
    assert segs[0]["words"][1]["word"] == "NAND-poort"
    assert {(f["from"], f["to"], f["count"]) for f in fixes} == {
        ("nent", "NAND", 1), ("NENT", "NAND", 1), ("ELU", "ALU", 1), ("boeliaanse", "booleaanse", 1)}


def test_common_words_are_never_replaced():
    segs = [seg("we gaan naar veel full vol, ook diep")]  # sound like NOR, VIL, DEP but are ordinary words
    assert apply_fixes(segs, TERMS + [{"term": "DEP", "source": "slides"}], {}) == []
    assert segs[0]["text"] == "we gaan naar veel full vol, ook diep"


def test_lowercase_words_stay_lowercase_unless_the_term_is_an_acronym():
    segs = [seg("de algebraische vorm met een nent")]
    apply_fixes(segs, TERMS, {})
    assert segs[0]["text"] == "de algebraïsche vorm met een NAND"


def test_course_fix_list_goes_first_and_matches_whole_words():
    segs = [seg("de Karno map en karnokaart, Nent poort")]
    fixes = apply_fixes(segs, TERMS, {"karno": "Karnaugh", "nent poort": "NAND-poort"})
    assert segs[0]["text"] == "de Karnaugh map en karnokaart, NAND-poort"
    assert [(f["kind"], f["from"], f["count"]) for f in fixes] == [("course", "nent poort", 1), ("course", "karno", 1)]
