"""Orchestrates the stages of a job with resume logic.

Stage order: audio → chunk → transcribe → stitch (later phases add more). A stage is skipped when
its manifest entry is "done" with the same input hash. Transcription is per STT run: each run
freezes its own chunk plan (stt/<run>/chunks.json), so changing chunk settings never silently
re-transcribes; only `redo` starts a new run.
"""

from __future__ import annotations

import threading
from collections import Counter
from pathlib import Path

from . import config as cfgmod
from . import fixes
from . import termfix
from .config import Config, Course
from .job import Job
from .providers.groq_stt import GroqSTT
from .ratelimit import Ledger, QuotaExhausted
from .report import LoggingReporter, Reporter
from .stages import s1_audio, s2_slides, s3_chunk, s4_transcribe, s5_stitch, s6_sections, s7_notes, s8_review
from .subtitles import build_cues, to_srt, to_vtt
from .util import fmt_ts, hash_data, read_json, write_json, write_text

STAGES = ["audio", "player", "slides", "chunk", "transcribe", "stitch", "sections", "study_pack", "review"]


def ledger() -> Ledger:
    return Ledger(cfgmod.cache_dir() / "ledger.json")


# The worker may transcribe several lectures at once (transcribe.parallel_lectures). The Mac's server queues
# requests itself, but the laptop GPU fits one model (8 GB VRAM) and Groq has per-minute limits: those are
# held by one lecture at a time, taken before the model loads and released when its transcription is done.
_EXCLUSIVE = {"local": threading.Lock(), "groq": threading.Lock()}


def _hold(name: str, make):
    lock = _EXCLUSIVE[name]
    lock.acquire()
    try:
        stt = make()
    except BaseException:
        lock.release()
        raise
    stt._release = lock.release  # called by _close()
    return stt


def _groq(conf: Config, reporter: Reporter) -> GroqSTT:
    key = cfgmod.load_keys()["GROQ_API_KEY"]
    if not key:
        raise RuntimeError(f"GROQ_API_KEY is empty — paste it in {cfgmod.env_path()}")
    return _hold("groq", lambda: GroqSTT(key, conf, ledger(), reporter))


def _local(conf: Config, reporter: Reporter):
    from .providers.local_whisper import LocalWhisper

    def make():
        stt = LocalWhisper(conf, reporter)
        stt.check()  # raises LocalUnavailable
        return stt
    return _hold("local", make)


def _mac(conf: Config, reporter: Reporter, model: str | None = None):
    from .providers.mac_whisper import MacUnavailable, MacWhisper

    token = cfgmod.load_keys()["LECTURE_MAC_TOKEN"]
    if not token:
        raise MacUnavailable(f"LECTURE_MAC_TOKEN is empty in {cfgmod.env_path()}")
    stt = MacWhisper(conf, token, reporter, model=model)
    stt.check()  # raises MacUnavailable (a RuntimeError) within stt.mac.health_timeout_s
    return stt


class _FixedModel:
    """A provider pinned to one model and named after its chain entry (models added in Settings)."""

    def __init__(self, inner, name: str, model: str):
        self.inner, self.name, self.model = inner, name, model

    def transcribe(self, audio_path, duration_s, language, prompt, model=None):
        return self.inner.transcribe(audio_path, duration_s, language, prompt, model=self.model)

    def close(self):
        if hasattr(self.inner, "close"):
            self.inner.close()


_STT_FACTORIES = {"mac": lambda conf, rep: _mac(conf, rep), "groq": lambda conf, rep: _groq(conf, rep),
                  "local": lambda conf, rep: _local(conf, rep)}


def stt_factory(name: str):
    """(conf, reporter) → provider for a chain entry: built-in, or "custom:<id>" (a model added in Settings)."""
    if not name.startswith("custom:"):
        return _STT_FACTORIES[name]

    def make(conf: Config, rep: Reporter):
        try:
            m = conf.model_entry(name)
        except StopIteration:
            raise RuntimeError(f"{name} is not in models: any more") from None
        if m.provider == "mac":
            stt = _mac(conf, rep, model=m.model)
            stt.name = name
            return stt
        return _FixedModel(_groq(conf, rep), name, m.model)
    return make


def on_battery() -> bool:
    from .status import on_battery as _on_battery
    return _on_battery()


def get_stt(conf: Config, rep: Reporter, preferred: str | None = None, skip: tuple[str, ...] = ()):
    """First working STT provider: `preferred` (a run's provider) first, then the configured chain,
    leaving out `skip` (providers that dropped out during this run)."""
    from .providers.local_whisper import LocalUnavailable

    chain = [preferred] if preferred else []
    chain += [p for p in conf.stt.providers if p not in chain and p not in skip]
    if "local" in chain[:-1] and conf.stt.local.skip_on_battery and on_battery():
        # hot + drains the battery: last resort (a lecture still gets done when Mac and Groq both fail)
        chain = [p for p in chain if p != "local"] + ["local"]
        rep.info("On battery: the laptop GPU is only used if nothing else works")
    errors = []
    for name in chain:
        try:
            stt = stt_factory(name)(conf, rep)
        except (LocalUnavailable, RuntimeError) as exc:
            errors.append(f"{name}: {exc}")
            rep.warn(f"Speech-to-text provider '{name}' unavailable: {exc}")
            continue
        if preferred and name != preferred:
            rep.warn(f"This run was started with '{preferred}' but continues with '{name}'")
        return stt
    raise RuntimeError("no speech-to-text provider available: " + "; ".join(errors))


def _close(stt) -> None:
    """Free provider resources (local Whisper's GPU memory) once a run's transcription is done, and let the
    next lecture use the provider (see _EXCLUSIVE)."""
    try:
        if hasattr(stt, "close"):
            stt.close()
    finally:
        release = getattr(stt, "_release", None) or getattr(getattr(stt, "inner", None), "_release", None)
        if release:
            stt._release = None
            if hasattr(stt, "inner"):
                stt.inner._release = None
            release()


# --- stages ------------------------------------------------------------------------------


def stage_audio(job: Job, conf: Config, rep: Reporter) -> None:
    h = s1_audio.input_hash(job, conf)
    if job.stage_done("audio", h) and job.full_audio.exists() and job.silences_path.exists():
        rep.info("Audio: already extracted")
        return
    if job.stage("audio") and job.current_run:
        rep.warn("Audio settings changed: the existing transcription run no longer matches the audio; "
                 "a new run will be started (uses Groq quota). Old runs are kept in stt/.")
        job.manifest["stt"]["current_run"] = None
        job.invalidate(STAGES[1:])
    s1_audio.run(job, conf, rep)


def stage_player(job: Job, conf: Config, rep: Reporter) -> None:
    """Browser-friendly copy of the video for the in-app player (re-pack, seconds; recordings with sparse
    keyframes are re-encoded on the AMD chip, minutes: see player.py)."""
    from .player import ensure_player

    media = Path(job.manifest["input"]["media"])
    out = ensure_player(job.root, media, reencode=True)  # the worker may take minutes (sparse keyframes)
    job.mark_stage("player", "done", copy=str(out) if out else None)


def job_course(job: Job) -> Course:
    """The job's course from courses.yaml (a bare stand-in if it was removed from there)."""
    for course in cfgmod.load_courses():
        if course.id == job.manifest["course"]:
            # an English guest lecture in a Dutch course: the term list and Whisper prompt follow the lecture
            return course if course.language == job.language else course.model_copy(update={"language": job.language})
    return Course(id=job.manifest["course"], name=job.manifest["course"], language=job.language,
                  notes_language=job.language)


def stage_slides(job: Job, conf: Config, rep: Reporter) -> None:
    course = job_course(job)
    h = s2_slides.input_hash(job, course, conf)
    if job.stage_done("slides", h) and (job.root / "terms.json").exists():
        rep.info("Slides: up to date")
        return
    result = s2_slides.run(job, course, conf, rep)
    job.mark_stage("slides", "done", h, terms=len(result["terms"]), section=result["lecture_section"])


def term_prompt(job: Job) -> str:
    path = job.root / "terms.json"
    return read_json(path)["whisper_prompt"] if path.exists() else ""


def create_run(job: Job, conf: Config, rep: Reporter, make_current: bool, target_s: float | None = None,
               time_range: tuple[float, float] | None = None, provider: str | None = None) -> str:
    """Plan chunks for a new STT run. A time_range makes a partial run (only chunks in that range)."""
    sil = read_json(job.silences_path)
    duration = sil["duration_s"]
    chunk_cfg = conf.chunking.model_copy(update={"target_s": target_s or conf.chunking.target_s})
    # Chunks are 16-bit mono 16 kHz FLAC: never more than ~32 kB/s (uncompressed PCM). Older jobs may
    # have a 24-bit full.flac, so cap the measured rate at that bound.
    bytes_per_s = min(job.full_audio.stat().st_size / max(duration, 1.0), 2 * s1_audio.SAMPLE_RATE)
    max_bytes = conf.chunking.max_chunk_mb * 2**20
    while True:
        plan = s3_chunk.plan_chunks(duration, [tuple(s) for s in sil["silences"]], chunk_cfg)
        longest = max((c["end"] - c["start"] for c in plan["chunks"]), default=0.0)
        if bytes_per_s * longest * 1.15 <= max_bytes:  # 15 % margin: speech compresses less than silence
            break
        if chunk_cfg.target_s * 0.75 < 60:
            raise RuntimeError("audio compresses too badly to fit the Groq file size limit")
        chunk_cfg = chunk_cfg.model_copy(update={"target_s": chunk_cfg.target_s * 0.75})
        rep.warn(f"Chunks would exceed {conf.chunking.max_chunk_mb} MB; target lowered to {chunk_cfg.target_s:.0f} s")

    chunk_ids = None
    if time_range:
        chunks = s3_chunk.select_range(s3_chunk.chunks_from_plan(plan), *time_range)
        if not chunks:
            raise ValueError("no speech in that time range")
        chunk_ids = [c.id for c in chunks]
    # the term prompt is frozen per run, like the provider: resuming never mixes prompts
    run_id = job.new_run(make_current, target_s=chunk_cfg.target_s, provider=provider, term_prompt=term_prompt(job),
                         audio_hash=job.stage("audio").get("input_hash"),
                         range=[time_range[0], time_range[1]] if time_range else None, chunk_ids=chunk_ids)
    write_json(job.run_dir(run_id) / "chunks.json", plan)
    n = len(chunk_ids) if chunk_ids is not None else len(plan["chunks"])
    skipped = sum(b - a for a, b in plan["skipped"])
    rep.info(f"Run {run_id}: {n} chunks of ~{chunk_cfg.target_s:.0f} s; skipping {skipped / 60:.1f} min of "
             "long silences")
    return run_id


def stage_chunk(job: Job, conf: Config, rep: Reporter) -> None:
    run_id = job.current_run
    if run_id and (job.run_dir(run_id) / "chunks.json").exists():
        rep.info(f"Chunks: using run {run_id}")
    else:
        run_id = create_run(job, conf, rep, make_current=True)
    job.mark_stage("chunk", "done", hash_data({"run": run_id}), run=run_id)


def provider_from_raw(job: Job, run_id: str) -> str | None:
    """Provider of a run's finished chunks, for runs made before the provider was recorded (None if no chunks)."""
    raws = sorted(job.run_dir(run_id).glob("raw_*.json"))
    if not raws:
        return None
    return "local" if read_json(raws[0])["request"]["model"].startswith("local:") else "groq"


def stage_transcribe(job: Job, conf: Config, rep: Reporter) -> None:
    run_id = job.current_run
    assert run_id is not None
    h = hash_data({"run": run_id, "repair": 2})
    if job.stage_done("transcribe", h) and not s4_transcribe.missing_chunks(job, run_id):
        rep.info(f"Transcription: run {run_id} complete")
        return
    job.mark_stage("transcribe", "running", run=run_id)
    info = job.run_info(run_id)
    if not info.get("provider"):
        info["provider"] = provider_from_raw(job, run_id)
    stt = get_stt(conf, rep, info.get("provider"))
    if not info.get("provider"):
        info["provider"] = stt.name
        job.save()
    from .providers.mac_whisper import MacUnavailable

    dropped: tuple[str, ...] = ()
    while True:
        rep.info(f"Speech-to-text: {stt.name}")
        try:
            # both resume per chunk/piece: after a switch only the missing work goes to the next provider
            s4_transcribe.transcribe_run(job, conf, run_id, stt, rep)
            unrepaired = s4_transcribe.repair_run(job, conf, run_id, stt, rep)
            break
        except MacUnavailable as exc:
            dropped += (stt.name,)
            rep.warn(f"'{stt.name}' dropped out ({exc}); the remaining chunks go to the next provider")
        finally:
            _close(stt)
        stt = get_stt(conf, rep, skip=dropped)
    for a, b in unrepaired:
        rep.warn(f"Speech at {fmt_ts(a)}–{fmt_ts(b)} could not be transcribed (Whisper stuck, retry failed)")
    job.mark_stage("transcribe", "done", h, run=run_id,
                   unrepaired=[[round(a, 1), round(b, 1)] for a, b in unrepaired])


def stitch_run(job: Job, conf: Config, run_id: str) -> dict:
    """Stitch a run in memory (works for partial runs too)."""
    return s5_stitch.stitch(s4_transcribe.run_chunks(job, run_id), job.run_dir(run_id), conf.stitch, job.language)


def stage_stitch(job: Job, conf: Config, rep: Reporter) -> None:
    run_id = job.current_run
    assert run_id is not None
    run_dir = job.run_dir(run_id)
    raws = sorted((p.name, p.stat().st_size) for p in [*run_dir.glob("raw_*.json"), *run_dir.glob("repair*.json")])
    course = job_course(job)
    terms = read_json(job.root / "terms.json")["terms"] if (job.root / "terms.json").exists() else []
    h = hash_data({"run": run_id, "raws": raws, "stitch": conf.stitch.model_dump(),
                   "subtitles": conf.subtitles.model_dump(), "fixes": [fixes.FIX_VERSION, terms, course.corrections],
                   "suggestions": termfix.accepted(job)})
    if job.stage_done("stitch", h) and (job.outputs / "transcript_raw.txt").exists():
        rep.info("Stitch: up to date")
        return
    result = stitch_run(job, conf, run_id)
    result["fixes"] = fixes.apply_fixes(result["segments"], terms, course.corrections)
    result["fixes"] += termfix.apply_accepted(result["segments"], termfix.accepted(job))
    if result["fixes"]:
        rep.info("Fixed words: " + ", ".join(f"{f['from']} → {f['to']} ({f['count']}×)" for f in result["fixes"][:12]))
    plan = read_json(run_dir / "chunks.json")
    write_json(job.root / "transcript_raw.json", {"run": run_id, "language": job.language,
                                                  "skipped": plan["skipped"], **result})
    segs = result["segments"]
    write_text(job.outputs / "transcript_raw.txt", "".join(f"[{fmt_ts(s['start'])}] {s['text']}\n" for s in segs))
    cues = build_cues(segs, conf.subtitles)
    write_text(job.outputs / "subtitles.srt", to_srt(cues))
    write_text(job.outputs / "subtitles.vtt", to_vtt(cues))

    removed = Counter(r["reason"] for r in result["removed"])
    masked = [r for r in result["removed"] if r["reason"] == "masked"]
    if masked:
        rep.warn(f"{sum(r['end'] - r['start'] for r in masked) / 60:.1f} min of speech has no transcript "
                 "(Whisper returned '***'): " + ", ".join(f"{fmt_ts(r['start'])}" for r in masked[:8]))
    flags = Counter(f for s in segs for f in s["flags"])
    rep.info(f"Transcript: {len(segs)} segments, {sum(len(s['text'].split()) for s in segs)} words; "
             f"removed {dict(removed) or 'none'}; flagged {dict(flags) or 'none'}")
    job.mark_stage("stitch", "done", h, segments=len(segs), removed=dict(removed), flags=dict(flags))


def stage_sections(job: Job, conf: Config, rep: Reporter) -> None:
    slides_path = job.slides_dir / "slides.json"
    h = hash_data({"stitch": job.stage("stitch").get("input_hash"), "slides": job.stage("slides").get("input_hash"),
                   "sections": conf.sections.model_dump(), "title": job.manifest.get("title"), "version": 2})
    if job.stage_done("sections", h) and (job.outputs / "transcript.md").exists():
        rep.info("Sections: up to date")
        return
    segments = read_json(job.root / "transcript_raw.json")["segments"]
    slides: list[dict] = []
    if slides_path.exists():
        data = read_json(slides_path)
        slides = [s for s in data["slides"] if not data["lecture_section"] or s["section"] == data["lecture_section"]]
    result = s6_sections.run(segments, slides, job.language, conf)
    write_json(job.root / "sections.json", result)
    many_files = len({s["file"] for s in slides}) > 1
    write_text(job.outputs / "transcript.md",
               s6_sections.render_markdown(result, segments, heading(job), job.language, many_files))
    secs = result["sections"]
    low = sum(s["low_confidence"] for s in secs)
    rep.info(f"Sections: {len(secs)} ({result['method']})" + (f", {low} uncertain" if low else "")
             + (f"; {len(result['slides_not_discussed'])} slides not discussed" if result["slides_not_discussed"] else ""))
    job.mark_stage("sections", "done", h, sections=len(secs), method=result["method"], uncertain=low)


def heading(job: Job) -> str:
    return " — ".join(x for x in (job.manifest.get("title"), job_course(job).name, job.manifest.get("date")) if x)


def notes_inputs(job: Job, conf: Config) -> list[s7_notes.SectionInput]:
    segments = read_json(job.root / "transcript_raw.json")["segments"]
    sections = read_json(job.root / "sections.json")["sections"]
    slides_path = job.slides_dir / "slides.json"
    slides = read_json(slides_path)["slides"] if slides_path.exists() else []
    return s7_notes.build_inputs(sections, segments, slides, job.language, conf)


def stage_study_pack(job: Job, conf: Config, rep: Reporter) -> None:
    if conf.notes.study_pack:
        write_text(job.outputs / "study_pack.md",
                   s7_notes.study_pack(notes_inputs(job, conf), heading(job), job_course(job), conf))


def stage_review(job: Job, conf: Config, rep: Reporter) -> None:
    write_text(job.outputs / "review.md", s8_review.render(job, heading(job)))


def notes_factory(conf: Config, rep: Reporter, entry: str):
    """() → LLM provider for a notes chain entry ("claude:<model>", "gemini:<model>", "custom:<id>");
    raises LLMUnavailable when it can't be used."""
    from .providers.llm import LLMUnavailable

    def make():
        provider, model = entry.split(":", 1)
        if provider == "custom":
            m = conf.model_entry(entry)
            provider, model = m.provider, m.model
            if provider == "openai":
                from .providers.openai_llm import OpenAICompatLLM
                return OpenAICompatLLM(conf, m, rep)
        if provider == "claude":
            from .providers.claude_cli import ClaudeCLI
            return ClaudeCLI(conf, model, rep)
        if provider == "gemini":
            from .providers.gemini_llm import GeminiLLM
            return GeminiLLM(conf, model, rep)
        raise LLMUnavailable(f"{provider} notes are not implemented yet")
    return make


def notes_providers(conf: Config, rep: Reporter, only: str | None = None) -> list[tuple[str, object]]:
    """llm.tasks.notes as (label, factory) pairs; factories raise LLMUnavailable when unusable."""
    out = []
    for entry in conf.llm.tasks["notes"]:
        if only is None or entry.split(":", 1)[0] == only:
            out.append((entry, notes_factory(conf, rep, entry)))
    if not out and only is None:  # no notes model chosen: the job waits with this reason (notes_pending)
        def none():
            from .providers.llm import LLMUnavailable
            raise LLMUnavailable("no notes model yet: add one in Settings › Models")
        return [("notes", none)]
    if not out:
        raise ValueError(f"no '{only}' entry in llm.tasks.notes")
    return out


def run_notes(job: Job, conf: Config, reporter: Reporter, provider: str | None = None) -> None:
    """Notes for a transcribed job. Raises s7_notes.NotesPending (job status notes_pending) when no
    provider can make them now; the free outputs (study pack, review) are written either way."""
    with job.lock():
        rep = LoggingReporter(reporter, job.logger())
        if job.stage("sections").get("status") != "done":
            raise RuntimeError("transcribe the lecture first (lecture resume)")
        rep.stage("notes")
        inputs = notes_inputs(job, conf)
        try:
            notes, records = s7_notes.make_notes(job.root / "notes", inputs, heading(job), job_course(job), conf,
                                                 notes_providers(conf, rep, provider), rep)
        except s7_notes.NotesPending as exc:
            job.mark_stage("notes", "pending", reason=str(exc),
                           resume_at=exc.resume_at.isoformat(timespec="minutes") if exc.resume_at else None)
            job.manifest["status"] = "notes_pending"
            job.save()
            stage_review(job, conf, rep)
            raise
        tags = f"{job.manifest['course']} {job.root.name}"
        for name, text in s7_notes.render_outputs(notes, inputs, heading(job), job_course(job).notes_language,
                                                  tags, s7_notes.enabled_extras(conf)).items():
            write_text(job.outputs / name, text)
        att = [a for r in records for a in r.get("attempts", []) if "model" in a]
        job.mark_stage("notes", "done", batches=len(records), providers=sorted({r["provider"] for r in records}),
                       input_tokens=sum(a["input_tokens"] for a in att),
                       output_tokens=sum(a["output_tokens"] for a in att),
                       elapsed_s=round(sum(a["elapsed_s"] for a in att), 1))
        job.manifest["status"] = "done"
        job.save()
        stage_review(job, conf, rep)
        rep.info(f"Notes: {len(notes.sections)} sections, {len(notes.glossary)} glossary terms, "
                 f"{len(notes.quiz)} quiz questions, {len(notes.flashcards)} flashcards")


STAGE_FUNCS = {"audio": stage_audio, "player": stage_player, "slides": stage_slides, "chunk": stage_chunk, "transcribe": stage_transcribe,
               "stitch": stage_stitch, "sections": stage_sections, "study_pack": stage_study_pack,
               "review": stage_review}


# --- entry points --------------------------------------------------------------------------


def _run_stages(job: Job, conf: Config, rep: Reporter) -> None:
    job.check_media()
    try:
        for name in STAGES:
            rep.stage(name)
            STAGE_FUNCS[name](job, conf, rep)
    except QuotaExhausted as exc:
        job.manifest["status"] = "waiting_quota"
        job.manifest["resume_at"] = exc.resume_at.isoformat(timespec="minutes")
        job.save()
        raise
    except BaseException as exc:
        job.manifest["status"] = "failed" if not isinstance(exc, KeyboardInterrupt) else "interrupted"
        job.manifest["error"] = f"{type(exc).__name__}: {exc}"
        job.save()
        raise
    job.manifest["status"] = "notes_pending" if job.stage("notes").get("status") == "pending" else "done"
    job.manifest.pop("error", None)
    job.manifest.pop("resume_at", None)
    job.save()


def open_job(conf: Config, media: Path, course_id: str, slides: list[Path] | None = None, title: str | None = None,
             date: str | None = None, new: bool = False, language: str | None = None) -> tuple[Job, bool, list[Path]]:
    """Existing job for this file + course (unless new), else a new one; slides copied in.
    language: spoken language of this lecture (default: the course's). Returns (job, created, added slide copies)."""
    from datetime import date as date_cls

    courses = {c.id: c for c in cfgmod.load_courses()}
    if course_id not in courses:
        raise ValueError(f"unknown course {course_id!r}; known: {', '.join(courses)}")
    job = None if new else Job.find(conf.paths.jobs_dir, media, course_id)
    created = job is None
    if created:
        job = Job.create(conf.paths.jobs_dir, media, course_id, language or courses[course_id].language,
                         title or media.stem, date or date_cls.today().isoformat())
    return job, created, job.add_slides(slides or [])


def run_job(job: Job, conf: Config, reporter: Reporter) -> None:
    with job.lock():
        _run_stages(job, conf, LoggingReporter(reporter, job.logger()))


def use_run(job: Job, conf: Config, run_id: str, reporter: Reporter) -> None:
    """Make an existing, complete STT run the main transcript (e.g. a local run made with redo --range)."""
    with job.lock():
        if run_id not in job.manifest["stt"]["runs"]:
            raise ValueError(f"unknown run {run_id!r}; runs: {', '.join(job.manifest['stt']['runs'])}")
        plan = read_json(job.run_dir(run_id) / "chunks.json")
        ids = job.run_info(run_id).get("chunk_ids")
        if ids is not None and len(ids) < len(plan["chunks"]):
            raise ValueError(f"run {run_id} only covers {len(ids)} of {len(plan['chunks'])} chunks")
        if s4_transcribe.missing_chunks(job, run_id):
            raise ValueError(f"run {run_id} is not finished; transcribe it first")
        rep = LoggingReporter(reporter, job.logger())
        rep.info(f"use run {run_id} (was {job.current_run})")
        job.manifest["stt"]["current_run"] = run_id
        job.invalidate(STAGES[STAGES.index("chunk"):])
        _run_stages(job, conf, rep)


def run_termfix(job: Job, conf: Config, reporter: Reporter, fresh: bool = False) -> dict:
    """Term fix suggestions from the LLM on the Mac (termfix.py). Raises MacUnavailable when it can't run now.
    Doesn't hold the job lock: it only writes termfix.json, and accepting waits until it is done."""
    from .providers.mac_llm import MacLlm
    from .providers.mac_whisper import MacUnavailable

    token = cfgmod.load_keys()["LECTURE_MAC_TOKEN"]
    if not token:
        raise MacUnavailable(f"LECTURE_MAC_TOKEN is empty in {cfgmod.env_path()}")
    llm = MacLlm(conf, token, conf.termfix.model)
    try:
        llm.check()
        rep = LoggingReporter(reporter, job.logger())
        rep.stage("suggestions")
        return termfix.suggest(job, conf, llm, job_course(job), rep, fresh=fresh)
    except MacUnavailable as exc:
        termfix.mark(job, "skipped", str(exc))
        raise
    except Exception as exc:
        termfix.mark(job, "failed", f"{type(exc).__name__}: {exc}")
        raise
    finally:
        llm.close()


def refix(job: Job, conf: Config, reporter: Reporter) -> None:
    """Apply the course's (changed) fix list to a finished transcript: stitch onwards, no speech-to-text."""
    with job.lock():
        rep = LoggingReporter(reporter, job.logger())
        for name in STAGES[STAGES.index("stitch"):]:
            rep.stage(name)
            STAGE_FUNCS[name](job, conf, rep)


def redo(job: Job, conf: Config, stage: str, reporter: Reporter, target_s: float | None = None,
         time_range: tuple[float, float] | None = None, provider: str | None = None) -> str | None:
    """Force a stage (and everything after it). Returns the new run id for chunk/transcribe."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; choose from {', '.join(STAGES)}")
    with job.lock():
        rep = LoggingReporter(reporter, job.logger())
        rep.info(f"redo {stage}" + (f" range {time_range}" if time_range else "") +
                 (f" target {target_s} s" if target_s else ""))
        if time_range:
            if stage not in ("chunk", "transcribe"):
                raise ValueError("--range only applies to the chunk/transcribe stage")
            job.check_media()
            run_id = create_run(job, conf, rep, make_current=False, target_s=target_s, time_range=time_range,
                                provider=provider)
            rep.stage("transcribe")
            stt = get_stt(conf, rep, provider)
            job.run_info(run_id)["provider"] = stt.name
            job.save()
            try:
                s4_transcribe.transcribe_run(job, conf, run_id, stt, rep)
                s4_transcribe.repair_run(job, conf, run_id, stt, rep)
            finally:
                _close(stt)
            return run_id
        run_id = None
        if stage == "audio":
            job.manifest["stt"]["current_run"] = None
        elif stage in ("chunk", "transcribe"):
            job.check_media()
            run_id = create_run(job, conf, rep, make_current=True, target_s=target_s, provider=provider)
        job.invalidate(STAGES[STAGES.index(stage):])
        _run_stages(job, conf, rep)
        return run_id
