"""End-to-end Phase 1 pipeline on synthetic audio with a fake Groq provider (offline, free)."""

import sys
import pytest

from lecture import pipeline
from lecture.job import Job
from lecture.providers.base import Transcription
from lecture.report import NullReporter
from lecture.util import read_json

from .conftest import make_audio


class FakeSTT:
    """Returns one segment per call; can be told to crash after n calls."""

    name = "fake"

    def __init__(self, crash_after=None):
        self.calls = []
        self.crash_after = crash_after

    def transcribe(self, audio_path, duration_s, language, prompt, model=None):
        if self.crash_after is not None and len(self.calls) >= self.crash_after:
            raise KeyboardInterrupt  # like the user killing the process
        n = len(self.calls)
        self.calls.append({"duration": duration_s, "prompt": prompt, "language": language})
        topics = ["de vraagcurve", "het aanbod", "elasticiteit", "de markt", "belastingen", "het IS-LM-model"]
        text = f"Nu bespreken we {topics[n % len(topics)]} in fragment {n}."
        toks = text.split()
        step = duration_s / len(toks)  # text spread over the whole chunk, like real speech
        return Transcription(
            response={"text": text,
                      "segments": [{"start": 0.0, "end": step * len(toks), "text": " " + text, "avg_logprob": -0.2,
                                    "no_speech_prob": 0.01, "compression_ratio": 1.1}],
                      "words": [{"word": t.strip(".,"), "start": i * step, "end": (i + 1) * step}
                                for i, t in enumerate(toks)]},
            model="whisper-large-v3", attempts=1)


@pytest.fixture
def lecture_job(tmp_path, xdg, monkeypatch):
    xdg.mkdir(parents=True)
    # small chunks so a short test file gives several chunks
    (xdg / "config.yaml").write_text(
        f"paths:\n  jobs_dir: {tmp_path / 'jobs'}\nchunking:\n  target_s: 60\n  search_window_s: 10\n")
    from lecture.config import load_config
    conf = load_config()
    # 0–20 s quiet (before class, skipped), speech with short pauses, a 25 s break, more speech
    pattern = [("quiet", 20)] + [("tone", 9), ("quiet", 1)] * 15 + [("quiet", 25)] + [("tone", 9), ("quiet", 1)] * 12
    media = make_audio(tmp_path / "les.mp4", pattern, video=True)
    job = Job.create(conf.paths.jobs_dir, media, "algemene-economie", "nl", "Les 1", "2026-10-14")
    return job, conf, media


def test_full_run_then_resume_after_kill(lecture_job, monkeypatch):
    job, conf, media = lecture_job
    fake = FakeSTT(crash_after=2)
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: fake)

    with pytest.raises(KeyboardInterrupt):
        pipeline.run_job(job, conf, NullReporter())
    job = Job(job.root)
    assert job.manifest["status"] == "interrupted"
    run_id = job.current_run
    assert len(list(job.run_dir(run_id).glob("raw_*.json"))) == 2

    fake2 = FakeSTT()
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: fake2)
    pipeline.run_job(job, conf, NullReporter())
    job = Job(job.root)
    plan = read_json(job.run_dir(run_id) / "chunks.json")
    n_chunks = len(plan["chunks"])
    assert len(fake2.calls) == n_chunks - 2          # finished chunks were not re-sent
    assert job.manifest["status"] == "done" and job.current_run == run_id

    # both long silences skipped: 0–19.5 s and the 25 s break
    skipped = plan["skipped"]
    assert skipped[0][0] == 0 and skipped[0][1] == pytest.approx(19.5, abs=0.2)
    assert any(b - a > 20 for a, b in skipped[1:])
    # chunks never cover skipped ranges
    for c in plan["chunks"]:
        for a, b in skipped:
            assert c["end"] <= a + 1e-6 or c["start"] >= b - 1e-6

    # prompt = course term sentence (no slides: extra_terms + lecturer), then the previous chunk's tail
    assert fake2.calls[0]["prompt"] == ("Dit is een les van Algemene Economie door Prof. Janssens over elasticiteit, "
                                        "IS-LM, Keynesiaans. Nu bespreken we het aanbod in fragment 1.")
    assert fake2.calls[0]["language"] == "nl"

    # outputs exist; timestamps are absolute (first chunk starts after the skipped intro)
    txt = (job.outputs / "transcript_raw.txt").read_text()
    assert txt.splitlines()[0].startswith("[00:00:19]")
    assert (job.outputs / "subtitles.srt").read_text().startswith("1\n00:00:19,")
    data = read_json(job.root / "transcript_raw.json")
    segs = data["segments"]
    assert data["removed"] == [] and len(segs) == n_chunks
    assert all(a["start"] < b["start"] for a, b in zip(segs, segs[1:]))
    # chunk audio is deleted after transcription (re-creatable)
    assert not list((job.run_dir(run_id) / "audio").glob("*.flac"))


def test_rerun_is_free_and_partial_redo_keeps_main_run(lecture_job, monkeypatch):
    job, conf, media = lecture_job
    fake = FakeSTT()
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: fake)
    pipeline.run_job(job, conf, NullReporter())
    first_calls = len(fake.calls)

    pipeline.run_job(Job(job.root), conf, NullReporter())   # everything done → no calls
    assert len(fake.calls) == first_calls

    job = Job(job.root)
    main = job.current_run
    new_run = pipeline.redo(job, conf, "transcribe", NullReporter(), time_range=(100.0, 130.0))
    job = Job(job.root)
    assert new_run != main and job.current_run == main
    assert 1 <= len(fake.calls) - first_calls <= 2
    assert job.run_info(new_run)["range"] == [100.0, 130.0]


def test_changed_media_is_refused(lecture_job, monkeypatch):
    job, conf, media = lecture_job
    with media.open("ab") as fh:
        fh.write(b"x")
    with pytest.raises(RuntimeError, match="changed"):
        pipeline.run_job(job, conf, NullReporter())


def test_job_is_found_again_for_same_file(lecture_job):
    job, conf, media = lecture_job
    assert Job.find(conf.paths.jobs_dir, media, "algemene-economie").root == job.root
    assert Job.find(conf.paths.jobs_dir, media, "data-science") is None


class StuckSTT(FakeSTT):
    """Whisper's real failure: the second half of a chunk comes back as '***'; alone it transcribes fine."""

    def transcribe(self, audio_path, duration_s, language, prompt, model=None):
        if "repair_" not in audio_path.name:
            self.calls.append({"duration": duration_s, "prompt": prompt, "model": model})
            half = duration_s / 2
            return Transcription(response={"text": " Goed. ***", "segments": [
                {"start": 0.0, "end": half, "text": " Goed, we beginnen met de opteller.", "avg_logprob": -0.2,
                 "no_speech_prob": 0.01, "compression_ratio": 1.1},
                {"start": half, "end": duration_s, "text": " *** *** ***", "avg_logprob": -0.1,
                 "no_speech_prob": 0.0, "compression_ratio": 1.0}], "words": []},
                model="whisper-large-v3", attempts=1)
        self.calls.append({"duration": duration_s, "prompt": prompt, "model": model, "repair": True})
        return Transcription(response={"text": " Een minterm per n-poort.", "segments": [
            {"start": 1.0, "end": duration_s - 1.0, "text": " Een minterm per n-poort.", "avg_logprob": -0.15,
             "no_speech_prob": 0.01, "compression_ratio": 1.1}], "words": []},
            model="whisper-large-v3", attempts=1)


def test_masked_output_is_repaired_and_not_used_as_prompt(lecture_job, monkeypatch):
    job, conf, media = lecture_job
    fake = StuckSTT()
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: fake)
    pipeline.run_job(job, conf, NullReporter())
    main = [c for c in fake.calls if not c.get("repair")]
    repairs = [c for c in fake.calls if c.get("repair")]
    assert repairs and all(c["prompt"] == "" for c in repairs)
    assert all(c["duration"] <= 60 * 1.5 + 2 for c in repairs)   # short pieces (+ padding)
    # '***' never leaks into the next chunk's prompt
    assert all("*" not in c["prompt"] for c in main)
    data = read_json(job.root / "transcript_raw.json")
    texts = [s["text"] for s in data["segments"]]
    assert not any("*" in t for t in texts)
    assert sum("repaired" in s["flags"] for s in data["segments"]) == len(repairs)
    assert "Een minterm per n-poort." in texts
    # rerun: repairs are not redone
    n = len(fake.calls)
    pipeline.run_job(Job(job.root), conf, NullReporter())
    assert len(fake.calls) == n


def test_stt_chain_falls_back_and_run_provider_is_sticky(xdg, monkeypatch):
    from lecture.config import load_config
    from lecture.providers.local_whisper import LocalUnavailable

    conf = load_config()
    made = []

    def local(conf, rep):
        raise LocalUnavailable("no CUDA")

    def groq(conf, rep):
        made.append("groq")
        return type("G", (), {"name": "groq"})()

    monkeypatch.setitem(pipeline._STT_FACTORIES, "local", local)
    monkeypatch.setitem(pipeline._STT_FACTORIES, "groq", groq)
    warnings = []
    rep = type("R", (NullReporter,), {"warn": lambda self, m: warnings.append(m)})()
    assert pipeline.get_stt(conf, rep).name == "groq"
    assert any("local" in w and "no CUDA" in w for w in warnings)
    # a run started with local that can't use it any more says so explicitly
    pipeline.get_stt(conf, rep, preferred="local")
    assert any("started with 'local'" in w for w in warnings)


def test_resume_of_run_without_provider_keeps_groq(lecture_job, monkeypatch):
    # runs made before providers were recorded (DEP les 4) resumed on local and became mixed
    job, conf, media = lecture_job
    fake = FakeSTT(crash_after=2)
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: fake)
    with pytest.raises(KeyboardInterrupt):
        pipeline.run_job(job, conf, NullReporter())
    job = Job(job.root)
    del job.run_info(job.current_run)["provider"]
    job.save()

    asked = []
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: asked.append(preferred) or FakeSTT())
    pipeline.run_job(Job(job.root), conf, NullReporter())
    assert asked[0] == "groq"


def test_use_run_switches_main_transcript_only_to_complete_runs(lecture_job, monkeypatch):
    job, conf, media = lecture_job
    monkeypatch.setattr(pipeline, "get_stt", lambda conf, rep, preferred=None: FakeSTT())
    pipeline.run_job(job, conf, NullReporter())
    job = Job(job.root)
    part = pipeline.redo(job, conf, "transcribe", NullReporter(), time_range=(0.0, 60.0))
    full = pipeline.redo(job, conf, "transcribe", NullReporter(), time_range=(0.0, 1e6))
    job.manifest["stt"]["current_run"] = "r1"
    job.save()

    with pytest.raises(ValueError, match="only covers"):
        pipeline.use_run(Job(job.root), conf, part, NullReporter())
    pipeline.use_run(Job(job.root), conf, full, NullReporter())
    assert Job(job.root).current_run == full
    assert read_json(job.root / "transcript_raw.json")["run"] == full


def test_slides_are_copied_once_and_originals_untouched(lecture_job, tmp_path):
    job, conf, media = lecture_job
    pdf = tmp_path / "les1.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    added = job.add_slides([pdf, pdf])
    assert len(added) == 1 and added[0].read_bytes() == pdf.read_bytes()
    assert Job(job.root).slides[0]["source"] == str(pdf.resolve())
    assert job.add_slides([pdf]) == []
    with pytest.raises(ValueError):
        job.add_slides([media])


def test_local_whisper_retries_smaller_compute_type_on_gpu_oom(xdg, tmp_path, monkeypatch):
    from lecture.config import load_config
    from lecture.providers import local_whisper as lw

    conf = load_config()
    stt = lw.LocalWhisper(conf)
    loads = []

    def fake_load(compute_types=None):
        if stt._model is None:
            stt._compute_type = (compute_types or conf.stt.local.compute_types)[0]
            stt._model = object()
            loads.append(stt._compute_type)
        return stt._model

    def fake_transcribe(audio, language, prompt):
        fake_load()  # like the real _transcribe
        if stt._compute_type == "float16":
            raise RuntimeError("CUDA failed with error out of memory")
        return "ok"

    monkeypatch.setattr(lw, "load_audio", lambda path: None)
    monkeypatch.setattr(stt, "_load", fake_load)
    monkeypatch.setattr(stt, "_transcribe", fake_transcribe)
    assert stt.transcribe(tmp_path / "a.flac", 1.0, "nl", "") == "ok"
    assert loads == ["float16", "int8_float16"]
    stt.close()
    assert stt._model is None

    # out of memory with the smallest type too: a clear error (resume later), not a silent provider switch
    def always_oom(audio, language, prompt):
        fake_load()
        raise RuntimeError("out of memory")

    monkeypatch.setattr(stt, "_transcribe", always_oom)
    with pytest.raises(RuntimeError, match="lecture resume"):
        stt.transcribe(tmp_path / "a.flac", 1.0, "nl", "")
    assert stt._model is None


def test_lecture_language_overrides_the_course(xdg, tmp_path):
    """An English lecture in a Dutch course: the job and its term prompt use English."""
    from lecture import config as cfgmod
    from lecture.pipeline import job_course, open_job

    xdg.mkdir(parents=True, exist_ok=True)
    (xdg / "config.yaml").write_text(f"paths:\n  jobs_dir: {tmp_path / 'jobs'}\n")  # never the real ~/Lectures
    media = tmp_path / "guest.mp4"
    media.write_bytes(b"x" * 100)
    conf = cfgmod.load_config()
    assert conf.paths.jobs_dir == tmp_path / "jobs"
    course = cfgmod.load_courses()[0]
    job, created, _ = open_job(conf, media, course.id, language="en" if course.language == "nl" else "nl")
    assert created and job.language != course.language
    assert job_course(job).language == job.language and job_course(job).name == course.name


def test_mac_drops_out_mid_lecture_rest_goes_to_next_provider(lecture_job, monkeypatch):
    from lecture.providers.mac_whisper import MacUnavailable

    job, conf, media = lecture_job

    class DroppingMac(FakeSTT):
        name = "mac"

        def transcribe(self, *a, **kw):
            if len(self.calls) >= 2:
                raise MacUnavailable("Mac stopped answering")
            return super().transcribe(*a, **kw)

    mac, local, asked = DroppingMac(), FakeSTT(), []
    local.name = "local"

    def get_stt(conf, rep, preferred=None, skip=()):
        asked.append(skip)
        return local if "mac" in skip else mac

    monkeypatch.setattr(pipeline, "get_stt", get_stt)
    pipeline.run_job(job, conf, NullReporter())
    job = Job(job.root)
    n_chunks = len(read_json(job.run_dir(job.current_run) / "chunks.json")["chunks"])
    assert job.manifest["status"] == "done" and asked == [(), ("mac",)]
    assert len(mac.calls) == 2 and len(local.calls) == n_chunks - 2   # nothing redone, nothing lost


@pytest.mark.skipif(sys.platform == "win32", reason="reads Linux sysfs")
def test_on_battery_the_laptop_gpu_is_last_resort(xdg, monkeypatch, tmp_path):
    from lecture.config import load_config
    from lecture.providers.local_whisper import LocalUnavailable
    from lecture.status import on_battery

    # sysfs as on the G14: charger (ACAD) offline, battery discharging; a USB-C charger counts as power too
    def supply(name, **files):
        (tmp_path / name).mkdir()
        for k, v in files.items():
            (tmp_path / name / k).write_text(v + "\n")
    supply("ACAD", type="Mains", online="0")
    supply("BAT1", type="Battery", status="Discharging")
    supply("ucsi-source-psy-USBC000:001", type="USB", online="0")
    assert on_battery(tmp_path)
    (tmp_path / "ucsi-source-psy-USBC000:001" / "online").write_text("1\n")
    assert not on_battery(tmp_path)

    conf = load_config()
    conf.stt.providers = ["mac", "local", "groq"]
    made = []

    def factory(name, ok=True):
        def make(conf, rep):
            made.append(name)
            if not ok:
                raise LocalUnavailable(f"{name} down") if name == "local" else RuntimeError(f"{name} down")
            return type("P", (), {"name": name})()
        return make

    monkeypatch.setattr(pipeline, "on_battery", lambda: True)
    monkeypatch.setitem(pipeline._STT_FACTORIES, "mac", factory("mac", ok=False))
    monkeypatch.setitem(pipeline._STT_FACTORIES, "local", factory("local"))
    monkeypatch.setitem(pipeline._STT_FACTORIES, "groq", factory("groq"))
    assert pipeline.get_stt(conf, NullReporter()).name == "groq" and made == ["mac", "groq"]  # GPU untouched
    made.clear()
    monkeypatch.setitem(pipeline._STT_FACTORIES, "groq", factory("groq", ok=False))
    assert pipeline.get_stt(conf, NullReporter()).name == "local" and made == ["mac", "groq", "local"]
    made.clear()
    conf.stt.local.skip_on_battery = False  # switched off in Settings: chain order as configured
    assert pipeline.get_stt(conf, NullReporter()).name == "local" and made == ["mac", "local"]


def test_run_with_chunk_prompts_and_carry(lecture_job, monkeypatch):
    from lecture.stages import s4_transcribe

    job, conf, media = lecture_job
    for stage in (pipeline.stage_audio, pipeline.stage_chunk):
        stage(job, conf, NullReporter())
    run_id = job.current_run
    info = job.run_info(run_id)
    info.update(term_prompt="Les over de markt.", chunk_prompts={"1": "Les over elasticiteit."}, carry_prompt=True)
    job.save()

    class CarryFake(FakeSTT):
        supports_carry = True

        def transcribe(self, audio_path, duration_s, language, prompt, model=None, carry_prompt=""):
            out = super().transcribe(audio_path, duration_s, language, prompt, model)
            self.calls[-1]["carry"] = carry_prompt
            return out

    fake = CarryFake()
    s4_transcribe.transcribe_run(job, conf, run_id, fake, NullReporter())
    assert [c["carry"] for c in fake.calls[:3]] == ["Les over de markt.", "Les over elasticiteit.", "Les over de markt."]
    assert fake.calls[1]["prompt"].startswith("Les over elasticiteit.")
    raw = read_json(job.run_dir(run_id) / "raw_001.json")["request"]
    assert raw["carry_prompt"] == "Les over elasticiteit."
    # a provider that can't repeat the prompt per window is refused instead of silently ignoring it
    for f in job.run_dir(run_id).glob("raw_*.json"):
        f.unlink()
    with pytest.raises(RuntimeError, match="repeats its prompt"):
        s4_transcribe.transcribe_run(job, conf, run_id, FakeSTT(), NullReporter())
