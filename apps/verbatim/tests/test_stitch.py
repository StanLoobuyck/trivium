from lecture.stages.s3_chunk import Chunk
from lecture.stages.s5_stitch import chunk_segments, collapse_repetitions, filter_segment, stitch
from lecture.util import write_json


def seg(start, end, text, **kw):
    return {"start": start, "end": end, "text": text, "avg_logprob": kw.get("lp", -0.2),
            "no_speech_prob": kw.get("ns", 0.01), "compression_ratio": kw.get("cr", 1.2)}


def words(*items):
    return [{"word": w, "start": a, "end": b} for w, a, b in items]


def raw(segments, word_list=(), prompt=""):
    return {"request": {"prompt": prompt}, "response": {"text": " ".join(s["text"] for s in segments),
                                                         "segments": list(segments), "words": list(word_list)}}


def test_offsets_by_chunk_start():
    c = Chunk(1, 600, 1200, 600, 1200, False)
    out = chunk_segments(c, raw([seg(0, 4, " Goed, we beginnen.")], words(("Goed", 0, 1), ("we", 1, 2), ("beginnen", 2, 4))))
    assert out[0]["start"] == 600 and out[0]["end"] == 604
    assert out[0]["words"][2]["start"] == 602
    assert out[0]["text"] == "Goed, we beginnen."


def test_hard_cut_keeps_words_by_midpoint(tmp_path, xdg):
    a = Chunk(0, 0, 601, 0, 600, True)
    b = Chunk(1, 599, 1200, 600, 1200, True)
    # chunk a hears "de prijselasticiteit van" across the cut at 600 s
    ra = raw([seg(595, 601, "kijken naar de prijselasticiteit")],
             words(("kijken", 595, 596), ("naar", 596, 597), ("de", 598, 599.5), ("prijselasticiteit", 599.5, 600.8)))
    # chunk b starts 1 s earlier (599 s absolute = 0 s local)
    rb = raw([seg(0, 3, "prijselasticiteit van de vraag")],
             words(("prijselasticiteit", 0.5, 1.8), ("van", 1.8, 2.2), ("de", 2.2, 2.4), ("vraag", 2.4, 3.0)))
    write_json(tmp_path / "raw_000.json", ra)
    write_json(tmp_path / "raw_001.json", rb)
    out = stitch([a, b], tmp_path, _cfg(), "nl")["segments"]
    text = " ".join(s["text"] for s in out)
    assert text.count("prijselasticiteit") == 1
    assert text == "kijken naar de prijselasticiteit van de vraag"


def test_partial_run_skips_missing_chunks(tmp_path, xdg):
    a = Chunk(0, 0, 600, 0, 600, False)
    b = Chunk(1, 600, 1200, 600, 1200, False)
    write_json(tmp_path / "raw_001.json", raw([seg(1, 3, "alleen dit")]))
    out = stitch([a, b], tmp_path, _cfg(), "nl")["segments"]
    assert [s["text"] for s in out] == ["alleen dit"] and out[0]["start"] == 601


def _cfg():
    from lecture.config import load_config
    return load_config().stitch


def _filter(s, prompt="", chunk_start=0.0):
    s = {**s, "flags": [], "words": []}
    return filter_segment(s, prompt, _cfg(), "nl", chunk_start), s


def test_phantom_phrases_removed_but_real_bedankt_kept(xdg):
    assert _filter(seg(10, 12, "Ondertiteld door de Amara.org gemeenschap"))[0] == "phantom"
    assert _filter(seg(10, 12, "Bedankt voor het kijken!"))[0] == "phantom"
    assert _filter(seg(10, 12, "Bedankt voor het kijken naar deze grafiek."))[0] is None


def test_prompt_echo_only_near_chunk_start(xdg):
    prompt = "en dan zien we dat de vraag daalt als de prijs stijgt in dit model"
    echo = seg(2, 6, "dan zien we dat de vraag daalt als de prijs stijgt")
    assert _filter(echo, prompt, chunk_start=0)[0] == "prompt_echo"
    later = seg(300, 304, "dan zien we dat de vraag daalt als de prijs stijgt")
    assert _filter(later, prompt, chunk_start=0)[0] is None


def test_flags(xdg):
    _, s = _filter(seg(0, 5, "iets", ns=0.9, lp=-1.5))
    assert "likely_no_speech" in s["flags"] and "low_confidence" in s["flags"]
    reason, s = _filter(seg(0, 5, "ja ja ja ja ja ja ja ja dus", cr=3.0))
    assert reason is None and s["text"] == "ja dus" and "repetition_collapsed" in s["flags"]


def test_collapse_repetitions_ngrams():
    assert collapse_repetitions("de vraag de vraag de vraag stijgt")[0] == "de vraag stijgt"
    assert collapse_repetitions("heel heel belangrijk")[0] == "heel heel belangrijk"  # 2× is normal speech


def test_suspect_spans_kinds(xdg):
    from lecture.config import load_config
    from lecture.stages.s4_transcribe import suspect_spans
    conf = load_config()
    chunk = Chunk(0, 100, 220, 100, 220, False)
    resp = {"segments": [
        seg(0, 10, "Goed, we beginnen."),
        seg(10, 40, "", ns=0.0),                       # empty (the real 19:00 failure)
        seg(60, 70, "Dit is normaal."),                # 40–60 s: gap with speech
        seg(70, 80, "kinds af sfeers off", lp=-2.1),   # garbled
        seg(80, 95, "Verder met de tabel."),
        seg(95, 120, "Prima."),
    ]}
    spans = suspect_spans(chunk, resp, silences=[], conf=conf)
    assert spans == [(110, 160, "lost"), (170, 180, "garbled")]
    # a gap that the silence map says is silent is not suspect
    assert suspect_spans(chunk, {"segments": [seg(0, 10, "a b c"), seg(60, 120, "d e f")]},
                         silences=[(109, 161)], conf=conf) == []


def test_judge_repair():
    from lecture.stages.s4_transcribe import judge_repair
    good = {"segments": [seg(0, 5, "kan je ze als sum of products voorstellen", lp=-0.3)]}
    assert judge_repair("lost", good, [])[0]
    assert not judge_repair("lost", {"segments": [seg(0, 5, "***")]}, [])[0]
    assert judge_repair("garbled", good, [seg(0, 5, "kinds af sfeers", lp=-2.1)])[0]
    worse = {"segments": [seg(0, 5, "iets anders", lp=-2.5)]}
    assert not judge_repair("garbled", worse, [seg(0, 5, "kinds af sfeers", lp=-2.1)])[0]


def test_repair_drops_duplicated_original_near_edge(tmp_path, xdg):
    """Real case: an original segment with squeezed timestamps holds text that the repair also has."""
    chunk = Chunk(0, 1000, 1500, 1000, 1500, False)
    write_json(tmp_path / "raw_000.json", raw([
        seg(389.0, 392.3, "Dus ik ga maar twee termen hebben in plaats van zes."),
        seg(392.3, 393.0, "Terwijl hier zal ik misschien liever product of sums doen, want ik heb maar drie nullen"),
        seg(393.0, 423.0, "*** ***", ns=0.0),
    ]))
    rep = raw([seg(1.0, 8.0, "Terwijl hier zal ik misschien liever product of sums doen, want ik heb maar drie nullen."),
               seg(8.0, 29.0, "Dus ik kan beter naar mijn maxtermen kijken.")])
    rep["request"] = {"start": 1392.0, "end": 1424.0, "keep_start": 1393.0, "keep_end": 1423.0}
    rep["accepted"] = True
    write_json(tmp_path / "repair_000_x.json", rep)
    write_json(tmp_path / "repairs.json", {"version": 2, "files": ["repair_000_x.json"]})
    texts = [s["text"] for s in stitch([chunk], tmp_path, _cfg(), "nl")["segments"]]
    assert sum(t.startswith("Terwijl hier") for t in texts) == 1
    assert texts[0].startswith("Dus ik ga maar twee termen")    # unrelated neighbour is kept
