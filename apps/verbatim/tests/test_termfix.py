"""Term fix suggestions (termfix.py, PLAN.md 8.7c): filters, a fake LLM, applying accepted ones, the Mac client."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from lecture import pipeline, termfix
from lecture.config import load_config
from lecture.job import Job
from lecture.providers.mac_llm import MacLlm
from lecture.providers.mac_whisper import MacUnavailable
from lecture.report import NullReporter
from lecture.util import read_json, write_json

from .test_pipeline import FakeSTT, lecture_job  # noqa: F401 — fixture

VOCAB = {"nand", "or", "xor", "poort", "logisch", "and"}


@pytest.mark.parametrize("wrong,right,why", [
    ("nent", "NAND", "ok"),
    ("off-poort", "OR-poort", "ok"),                  # "off" is common English, but not common Dutch
    ("of", "OR", "common words"),                     # every "of" in the part would become OR
    ("N", "NAND", "common words"),
    ("aritmetisch", "logisch", "doesn't sound alike"),
    ("nent", "NAND-poort met inverter", "not a slide term"),
    ("nent", "nent", "empty/same"),
    ("ixor", "XOR", "not in text"),
])
def test_verdict(wrong, right, why):
    text = "een nent of een off-poort, N keer aritmetisch"
    assert termfix.verdict(wrong, right, text, VOCAB, "nl") == why


class FakeLlm:
    model = "fake:1b"

    def __init__(self, answers):
        self.answers, self.prompts = answers, []

    def chat_json(self, prompt):
        self.prompts.append(prompt)
        return {"fixes": self.answers[len(self.prompts) - 1]}


def make_job(tmp_path) -> Job:
    media = tmp_path / "les.mp4"
    media.write_bytes(b"x" * 100)
    job = Job.create(tmp_path / "jobs", media, "digitale-elektronica", "nl", "Les 4", "2026-02-26")
    job.slides_dir.mkdir()
    write_json(job.slides_dir / "slides.json", {"slides": [
        {"id": 1, "file": "a.pdf", "page": 1, "title": "NAND", "text": "NAND-poort en NOR-poort", "notes": ""},
        {"id": 2, "file": "a.pdf", "page": 2, "title": "OR", "text": "OR-poort", "notes": ""}]})
    write_json(job.root / "sections.json", {"sections": [
        {"start": 0, "end": 100, "slides": [{"file": "a.pdf", "page": 1}]},
        {"start": 100, "end": 200, "slides": [{"file": "a.pdf", "page": 2}]}]})
    write_json(job.root / "transcript_raw.json", {"run": "r1", "segments": [
        {"start": 10, "end": 20, "text": " Een nent-poort is een off-poort met een inverter."},
        {"start": 30, "end": 40, "text": " Nog een nent."},
        {"start": 110, "end": 120, "text": " Hier een off-poort."}]})
    return job


def test_suggest_keeps_only_safe_pairs_per_part_and_resumes(tmp_path, xdg):
    job, conf = make_job(tmp_path), load_config()
    course = SimpleNamespace(name="DEP", corrections={})
    llm = FakeLlm([
        [{"wrong": "nent", "right": "NAND"}, {"wrong": "nent", "right": "NAND"}, {"wrong": "off-poort",
         "right": "NOR-poort"}, {"wrong": "een", "right": "NAND"}, "junk"],
        [{"wrong": "off-poort", "right": "OR-poort"}]])
    data = termfix.suggest(job, conf, llm, course)
    assert "NAND-poort en NOR-poort" in llm.prompts[0] and "Hier een off-poort." in llm.prompts[1]
    got = [(s["wrong"], s["right"], s["count"], s["start"], s["status"]) for s in data["suggestions"]]
    # the same words get a different term per part: that is why they are suggestions, not fixes
    assert got == [("nent", "NAND", 2, 0, "open"), ("off-poort", "NOR-poort", 1, 0, "open"),
                   ("off-poort", "OR-poort", 1, 100, "open")]
    assert data["refused"] == {"common words": 1} and data["status"] == "done"
    assert data["suggestions"][0]["at"] == 10 and "nent-poort" in data["suggestions"][0]["context"]

    # an interrupted run resumes from the stored answers (no second call for part 1)
    stored = read_json(termfix.path(job))
    stored.update(status="running", suggestions=[])
    stored["answers"].pop(next(k for k in stored["answers"] if k.startswith("100")))
    write_json(termfix.path(job), stored)
    llm2 = FakeLlm([[{"wrong": "off-poort", "right": "OR-poort"}]])
    assert len(termfix.suggest(job, conf, llm2, course)["suggestions"]) == 3 and len(llm2.prompts) == 1


def test_no_slides_is_skipped(tmp_path, xdg):
    job = make_job(tmp_path)
    (job.root / "sections.json").unlink()
    data = termfix.suggest(job, load_config(), FakeLlm([]), SimpleNamespace(name="DEP", corrections={}))
    assert data["status"] == "skipped" and data["suggestions"] == []


def test_accepted_suggestion_only_changes_its_own_part():
    segs = [{"start": 10, "end": 20, "text": "een off-poort", "words": [{"word": "off-poort"}]},
            {"start": 110, "end": 120, "text": "een off-poort"}]
    report = termfix.apply_accepted(segs, [{"wrong": "off-poort", "right": "NOR-poort", "start": 0, "end": 100}])
    assert [s["text"] for s in segs] == ["een NOR-poort", "een off-poort"] and segs[0]["words"][0]["word"] == "NOR-poort"
    assert report == [{"kind": "suggestion", "from": "off-poort", "to": "NOR-poort", "count": 1}]


def test_refix_applies_accepted_suggestions(lecture_job, monkeypatch):  # noqa: F811
    job, conf, _ = lecture_job
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: FakeSTT())
    pipeline.run_job(job, conf, NullReporter())
    segs = read_json(job.root / "transcript_raw.json")["segments"]
    first, last = segs[0], segs[-1]
    assert "fragment" in first["text"] and "fragment" in last["text"]
    write_json(termfix.path(job), {"status": "done", "suggestions": [
        {"id": "s1", "wrong": "fragment", "right": "FRAGMENT", "start": first["start"], "end": first["end"] + 0.01,
         "status": "open"}]})
    termfix.set_status(job, "s1", "accepted")
    pipeline.refix(Job(job.root), conf, NullReporter())
    tr = read_json(job.root / "transcript_raw.json")
    assert "FRAGMENT" in tr["segments"][0]["text"] and "fragment" in tr["segments"][-1]["text"]
    assert {"kind": "suggestion", "from": "fragment", "to": "FRAGMENT", "count": 1} in tr["fixes"]
    with pytest.raises(ValueError):
        termfix.set_status(job, "s1", "maybe")


def test_mac_llm_check_and_json_from_chatty_answer(xdg):
    conf = load_config()

    def client(handler):
        return httpx.Client(base_url=conf.stt.mac.url, transport=httpx.MockTransport(handler))

    old_server = client(lambda r: httpx.Response(200, json={"ok": True, "models": ["large-v3"]}))
    with pytest.raises(MacUnavailable, match="too old"):
        MacLlm(conf, "t", "qwen3.8:27b", client=old_server).check()
    no_model = client(lambda r: httpx.Response(200, json={"ok": True, "llm_models": ["gemma4:12b"]}))
    with pytest.raises(MacUnavailable, match="doesn't have"):
        MacLlm(conf, "t", "qwen3.8:27b", client=no_model).check()

    def handler(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "llm_models": ["qwen3.8:27b"]})
        body = json.loads(request.content)
        assert body["model"] == "qwen3.8:27b" and body["think"] is False and "format" not in body
        return httpx.Response(200, json={"message": {"content": 'Hier: {"fixes": [{"wrong": "nent", "right": "NAND"}]} klaar'}})

    llm = MacLlm(conf, "t", "qwen3.8:27b", client=client(handler))
    llm.check()
    assert llm.chat_json("…") == {"fixes": [{"wrong": "nent", "right": "NAND"}]}


@pytest.mark.parametrize("health,ok,detail", [
    ((None, "Mac at x not reachable"), False, "Mac at x not reachable"),
    (({"models": ["large-v3"]}, ""), False, "too old"),
    (({"llm_models": []}, ""), False, "isn't running"),
    (({"llm_models": ["gemma4:12b"]}, ""), False, "doesn't have qwen3.8:27b"),
    (({"llm_models": ["qwen3.8:27b"]}, ""), True, "online"),
])
def test_termfix_status_for_sidebar(xdg, monkeypatch, health, ok, detail):
    from lecture import models

    monkeypatch.setattr(models, "mac_health", lambda conf: health)
    got = models.termfix_status(load_config())
    assert got[0] is ok and detail in got[1]


def test_make_again_asks_anew_and_keeps_decisions(tmp_path, xdg):
    """2026-10-25: "make them again" reused the stored answers and dropped the user's choices (0 suggestions)."""
    job, conf = make_job(tmp_path), load_config()
    course = SimpleNamespace(name="DEP", corrections={})
    first = FakeLlm([[{"wrong": "nent", "right": "NAND"}, {"wrong": "off-poort", "right": "NOR-poort"}],
                     [{"wrong": "off-poort", "right": "OR-poort"}]])
    termfix.suggest(job, conf, first, course)
    termfix.set_status(job, "s1", "course")      # nent → NAND, every lecture
    termfix.set_status(job, "s2", "rejected")    # off-poort → NOR-poort in part 1
    again = FakeLlm([[{"wrong": "off-poort", "right": "NOR-poort"}, {"wrong": "nent", "right": "NAND"}],
                     [{"wrong": "off-poort", "right": "OR-poort"}]])
    data = termfix.suggest(job, conf, again, course, fresh=True)
    assert len(again.prompts) == 2                              # really asked again
    got = {(x["id"], x["wrong"], x["right"], x["status"]) for x in data["suggestions"]}
    assert got == {("s1", "nent", "NAND", "course"), ("s2", "off-poort", "NOR-poort", "rejected"),
                   ("s3", "off-poort", "OR-poort", "open")}  # decided ones stay, and don't come back as new
    # without fresh (worker resume) nothing is asked when all parts are answered
    assert len(termfix.suggest(job, conf, FakeLlm([]), course)["suggestions"]) == 3
