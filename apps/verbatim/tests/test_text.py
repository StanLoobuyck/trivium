import pytest

from lecture.config import load_config
from lecture.evaluate import evaluate, hypothesis_text, pooled
from lecture.providers.groq_stt import parse_wait_seconds
from lecture.subtitles import build_cues, to_srt, to_vtt
from lecture.stages.s4_transcribe import tail_words
from lecture.textnorm import is_masked, normalize_words


def test_normalize_dutch():
    assert normalize_words("Euh, de IS-LM-curve: [?Keynes?] zei eenentwintig, één keer!", "nl") == \
        ["de", "is", "lm", "curve", "keynes", "zei", "21", "1", "keer"]


def test_normalize_english_numbers():
    assert normalize_words("Twenty-one models, um, and 3.000 rows", "en") == ["21", "models", "and", "3000", "rows"]


def test_wer_and_term_recall():
    ref = "de prijselasticiteit van de vraag volgens Keynes"
    hyp = "de prijs elasticiteit van de vraag volgens keynes"
    r = evaluate("x", ref, hyp, ["prijselasticiteit", "Keynes", "IS-LM"], "nl")
    assert r.ref_words == 7
    assert r.substitutions == 1 and r.insertions == 1 and r.wer == pytest.approx(2 / 7)
    assert (r.term_hits, r.term_total) == (1, 2)   # IS-LM not in reference → not counted


def test_pooled_wer_weights_by_reference_length():
    a = evaluate("a", "een twee drie vier", "een twee drie vier", [], "nl")
    b = evaluate("b", "vijf zes", "vijf", [], "nl")
    assert pooled([a, b]).wer == pytest.approx(1 / 6)


def test_hypothesis_range_by_word_midpoint():
    segs = [{"start": 0, "end": 4, "text": "a b c d", "words": [
        {"word": w, "start": i, "end": i + 1} for i, w in enumerate("abcd")]}]
    assert hypothesis_text(segs, 1.0, 3.0) == "b c"


def test_subtitles_line_length_and_no_overlap(xdg):
    cfg = load_config().subtitles
    text = ("Goed, we gaan nu kijken naar de prijselasticiteit van de vraag. Dat is een belangrijk begrip "
            "voor het examen, dus let goed op wat ik nu ga zeggen over de berekening.")
    segs = [{"start": 10.0, "end": 22.0, "text": text, "words": []},
            {"start": 22.0, "end": 22.3, "text": "Oké.", "words": []}]
    cues = build_cues(segs, cfg)
    for c in cues:
        lines = c.text.split("\n")
        assert len(lines) <= 2 and all(len(line) <= 42 for line in lines)
        assert c.end - c.start <= cfg.max_cue_s + 1e-6
    assert all(a.end <= b.start + 1e-9 for a, b in zip(cues, cues[1:]))
    srt = to_srt(cues)
    assert srt.startswith("1\n00:00:10,000 --> ")
    assert to_vtt(cues).startswith("WEBVTT\n\n00:00:10.000 --> ")


def test_parse_groq_wait():
    assert parse_wait_seconds({"retry-after": "12"}, "") == 12
    msg = "Rate limit reached ... on seconds of audio per hour (ASH): Limit 7200, Used 7100. Please try again in 12m3.5s."
    assert parse_wait_seconds({}, msg) == pytest.approx(723.5)
    assert parse_wait_seconds({}, "try again in 1h2m") == 3720
    assert parse_wait_seconds({}, "nothing here") is None


def test_masked_detection():
    assert is_masked("***") and is_masked(" *** *** ***") and is_masked("*** **** De")
    assert not is_masked("De XOR-poort") and not is_masked("...") and not is_masked("2*3 is 6")


def test_prompt_tail_skips_masked_text():
    assert tail_words("Goed, we beginnen. *** *** ***", 40) == ""            # too few real words
    assert tail_words("een twee drie vier vijf zes *** ***", 5) == "twee drie vier vijf zes"
