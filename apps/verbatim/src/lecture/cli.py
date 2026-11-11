"""Command-line interface (`lecture …`)."""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__

app = typer.Typer(help="Lecture Transcriber: slide-aligned transcripts and study notes.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Lecture Transcriber."""


@app.command()
def version() -> None:
    """Print the version."""
    typer.echo(__version__)


@app.command()
def doctor(
    offline: bool = typer.Option(False, "--offline", help="Skip all network checks."),
    no_calls: bool = typer.Option(
        False, "--no-calls", help="List models but make no test calls (saves 1 Gemini request + 10 s Groq audio)."
    ),
) -> None:
    """Check ffmpeg, Python env, config, API keys; list live models and quotas."""
    from .doctor import ICONS, run_doctor

    checks = run_doctor(online=not offline, calls=not no_calls)
    width = max(len(c.name) for c in checks)
    for c in checks:
        typer.echo(f"{ICONS[c.status]} {c.name.ljust(width)}  {c.detail}")
    failed = [c for c in checks if c.status == "fail"]
    typer.echo()
    if failed:
        typer.echo(f"{len(failed)} problem(s) found.")
        raise typer.Exit(1)
    typer.echo("All required checks passed.")


# --- console progress ------------------------------------------------------------------------


class ConsoleReporter:
    """Prints stage headers and info lines; progress overwrites one line on a terminal."""

    def __init__(self) -> None:
        import sys

        self.tty = sys.stdout.isatty()
        self._last_pct = -1
        self._open_line = False

    def _end_line(self) -> None:
        if self._open_line:
            typer.echo()
            self._open_line = False

    def stage(self, name: str) -> None:
        self._end_line()
        self._last_pct = -1
        typer.secho(f"▸ {name}", bold=True)

    def progress(self, done: float, total: float, text: str = "") -> None:
        pct = int(100 * done / total) if total else 100
        if self.tty:
            typer.echo(f"\r  {text} {pct:3d}%", nl=False)
            self._open_line = True
        elif pct // 10 != self._last_pct // 10:
            typer.echo(f"  {text} {pct}%")
        self._last_pct = pct

    def info(self, message: str) -> None:
        self._end_line()
        typer.echo(f"  {message}")

    def warn(self, message: str) -> None:
        self._end_line()
        typer.secho(f"  ⚠ {message}", fg="yellow")


def _parse_range(text: str) -> tuple[float, float]:
    from .util import parse_ts

    a, sep, b = text.partition("-")
    if not sep:
        raise typer.BadParameter("use START-END, e.g. 00:41:00-00:46:00")
    start, end = parse_ts(a), parse_ts(b)
    if end <= start:
        raise typer.BadParameter("END must be after START")
    return start, end


def _execute(job, action) -> None:
    """Run a pipeline action with consistent messages, notifications and exit codes."""
    from .job import JobLockedError
    from .notify import notify
    from .ratelimit import QuotaExhausted, resume_time_text
    from .stages.s7_notes import NotesPending

    name = job.root.name
    try:
        action()
    except QuotaExhausted as exc:
        msg = f"{exc.window} limit reached. Run again {resume_time_text(exc.resume_at)}: lecture resume {job.root}"
        typer.secho(f"\n⏸ {msg}", fg="yellow")
        notify("Lecture paused (free quota)", f"{name}: {msg}")
        raise typer.Exit(3) from None
    except JobLockedError as exc:
        typer.secho(f"\n{exc}", fg="red")
        raise typer.Exit(4) from None
    except NotesPending as exc:  # not a failure: the transcript is done, the notes wait for budget/login
        when = f" Try again {resume_time_text(exc.resume_at)}." if exc.resume_at else ""
        typer.secho(f"\n⏸ Notes pending: {exc}.{when}\n  Meanwhile: {job.outputs / 'study_pack.md'}", fg="yellow")
        notify("Lecture notes pending", f"{name}: {exc}")
        raise typer.Exit(3) from None
    except KeyboardInterrupt:
        typer.secho(f"\nInterrupted. Resume with: lecture resume {job.root}", fg="yellow")
        raise typer.Exit(130) from None
    except Exception as exc:
        typer.secho(f"\n✖ {type(exc).__name__}: {exc}", fg="red")
        typer.echo(f"  Details in {job.root / 'log.txt'}. Resume with: lecture resume {job.root}")
        job.logger().exception("job failed")
        notify("Lecture failed", f"{name}: {exc}", urgency="critical")
        raise typer.Exit(1) from None
    typer.secho(f"\n✔ Done: {job.outputs}", fg="green")
    notify("Lecture ready", name)


# --- pipeline commands -------------------------------------------------------------------------


@app.command()
def run(
    media: Path = typer.Argument(..., exists=True, dir_okay=False, help="Lecture video or audio file."),
    course: str = typer.Option(..., "--course", "-c", help="Course id from courses.yaml."),
    slides: list[Path] = typer.Option(None, "--slides", "-s", exists=True, dir_okay=False,
                                      help="Slide file (PDF/PPTX); repeat for several."),
    title: str = typer.Option(None, "--title", help="Lecture title, e.g. 'Les 5' (default: file name)."),
    date: str = typer.Option(None, "--date", help="YYYY-MM-DD (default: today)."),
    new: bool = typer.Option(False, "--new", help="Start a new job even if this file was processed before."),
) -> None:
    """Process a lecture (resumes an existing job for the same file and course)."""
    from . import config as cfgmod
    from .pipeline import open_job, run_job

    conf = cfgmod.load_config()
    try:
        job, created, added = open_job(conf, media, course, slides, title, date, new)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--course") from None
    typer.echo(f"{'New job' if created else 'Resuming existing job'} {job.root}")
    for copy in added:
        typer.echo(f"Slides added: {copy.name}")
    _execute(job, lambda: run_job(job, conf, ConsoleReporter()))


@app.command()
def resume(job_dir: Path = typer.Argument(..., exists=True, file_okay=False)) -> None:
    """Continue a job where it stopped."""
    from . import config as cfgmod
    from .job import Job
    from .pipeline import run_job

    conf = cfgmod.load_config()
    job = Job(job_dir)
    _execute(job, lambda: run_job(job, conf, ConsoleReporter()))


@app.command()
def redo(
    job_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    stage: str = typer.Option(..., "--stage", help="audio | chunk | transcribe | stitch (and everything after)."),
    range_: str = typer.Option(None, "--range", help="START-END: new partial transcription run of only this "
                               "time range (for eval / experiments); the main transcript is not changed."),
    chunk_target: float = typer.Option(None, "--chunk-target", help="Chunk length (s) for the new run."),
    provider: str = typer.Option(None, "--provider", help="Speech-to-text for the new run: mac | local | groq."),
) -> None:
    """Force a stage again. transcribe/chunk start a new STT run (uses Groq quota)."""
    from . import config as cfgmod
    from .job import Job
    from .pipeline import redo as redo_stage

    conf = cfgmod.load_config()
    job = Job(job_dir)
    time_range = _parse_range(range_) if range_ else None
    result: dict = {}
    if provider not in (None, "mac", "local", "groq"):
        raise typer.BadParameter("choose mac, local or groq", param_hint="--provider")
    _execute(job, lambda: result.update(
        run=redo_stage(job, conf, stage, ConsoleReporter(), chunk_target, time_range, provider)))
    if result.get("run"):
        typer.echo(f"New STT run: {result['run']}" + (" (partial; evaluate with --run)" if time_range else ""))


@app.command()
def use(
    job_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    run_id: str = typer.Argument(..., help="Run id, e.g. r2 (see `lecture compare`)."),
) -> None:
    """Make an existing complete STT run the main transcript and rebuild the outputs."""
    from . import config as cfgmod
    from .job import Job
    from .pipeline import use_run

    conf = cfgmod.load_config()
    job = Job(job_dir)
    _execute(job, lambda: use_run(job, conf, run_id, ConsoleReporter()))


@app.command()
def notes(
    job_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    provider: str = typer.Option(None, "--provider", help="Only this provider from llm.tasks.notes: claude | gemini."),
    study_pack_only: bool = typer.Option(False, "--study-pack-only", help="Only write outputs/study_pack.md (free)."),
) -> None:
    """Study notes for a transcribed lecture (uses Claude / Gemini; finished batches are reused)."""
    from . import config as cfgmod
    from .job import Job
    from .pipeline import run_notes, stage_study_pack

    conf = cfgmod.load_config()
    job = Job(job_dir)
    if study_pack_only:
        stage_study_pack(job, conf.model_copy(update={"notes": conf.notes.model_copy(update={"study_pack": True})}),
                         ConsoleReporter())
        typer.echo(f"Study pack: {job.outputs / 'study_pack.md'}")
        return
    _execute(job, lambda: run_notes(job, conf, ConsoleReporter(), provider))


@app.command()
def suggest(
    job_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    model: str = typer.Option(None, "--model", help="Ollama model on the Mac (default: termfix.model)."),
    again: bool = typer.Option(False, "--again", help="Ask the model again (your decisions are kept)."),
) -> None:
    """Term fix suggestions from the LLM on the Mac; review them in the lecture's Suggestions tab."""
    from . import config as cfgmod
    from . import termfix
    from .job import Job
    from .pipeline import run_termfix
    from .util import fmt_ts

    conf = cfgmod.load_config()
    if model:
        conf = conf.model_copy(update={"termfix": conf.termfix.model_copy(update={"model": model})})
    job = Job(job_dir)
    old = termfix.load(job)
    if old and old.get("status") == "done" and not again:
        typer.echo(f"Already made ({len(old['suggestions'])} suggestions); --again remakes them.")
        return
    try:
        data = run_termfix(job, conf, ConsoleReporter(), fresh=again)
    except Exception as exc:
        typer.secho(f"✖ {type(exc).__name__}: {exc}", fg="red")
        raise typer.Exit(1) from None
    for s in data["suggestions"]:
        typer.echo(f"  {s['id']:>4} {fmt_ts(s['at'])}  {s['wrong']} → {s['right']}  ({s['count']}×)")
    typer.echo(f"{len(data['suggestions'])} suggestions, {data['proposed']} proposed, "
               f"{data['elapsed_s'] / 60:.1f} min; refused: {data['refused']}")


@app.command("eval")
def eval_(
    ref: Path = typer.Argument(..., exists=True, dir_okay=False,
                               help="Reference .txt (with JOB_DIR --start --end), or a .yaml list of references."),
    job_dir: Path = typer.Argument(None, file_okay=False),
    start: str = typer.Option(None, "--start", help="Start of the reference in the recording (HH:MM:SS)."),
    end: str = typer.Option(None, "--end", help="End of the reference (HH:MM:SS)."),
    run_id: str = typer.Option(None, "--run", help="STT run to evaluate (default: the job's current run)."),
    terms: str = typer.Option(None, "--terms", help="Comma-separated terms for term recall "
                              "(default: course extra_terms + lecturer)."),
) -> None:
    """WER and term recall of a transcript against hand-made reference(s)."""
    import yaml

    from . import config as cfgmod
    from .evaluate import evaluate, hypothesis_text, job_segments, pooled, read_reference
    from .job import Job
    from .util import parse_ts

    conf = cfgmod.load_config()
    courses = {c.id: c for c in cfgmod.load_courses()}
    if ref.suffix in (".yaml", ".yml"):
        base = ref.parent
        items = [{**i, "ref": base / i["ref"], "job": base / i["job"]} for i in yaml.safe_load(ref.read_text(encoding="utf-8"))]
    else:
        if not (job_dir and start and end):
            raise typer.BadParameter("a .txt reference needs JOB_DIR, --start and --end")
        items = [{"ref": ref, "job": job_dir, "start": start, "end": end}]

    results = []
    for item in items:
        job = Job(Path(item["job"]))
        course = courses.get(job.manifest["course"])
        term_list = [t.strip() for t in terms.split(",")] if terms else (
            (course.extra_terms + ([course.lecturer] if course.lecturer else [])) if course else [])
        a, b = parse_ts(str(item["start"])), parse_ts(str(item["end"]))
        segments = job_segments(job, conf, item.get("run", run_id))
        hyp = hypothesis_text(segments, a, b)
        label = f"{Path(item['ref']).name} [{item['start']}–{item['end']}]"
        results.append(evaluate(label, read_reference(Path(item["ref"])), hyp, term_list, job.language))
    if len(results) > 1:
        results.append(pooled(results))

    typer.echo(f"{'reference':<44} {'words':>6} {'WER':>7} {'sub':>5} {'del':>5} {'ins':>5}  term recall")
    for r in results:
        recall = f"{r.term_recall:.0%} ({r.term_hits}/{r.term_total})" if r.term_recall is not None else "–"
        typer.echo(f"{r.label[:44]:<44} {r.ref_words:>6} {r.wer:>7.2%} {r.substitutions:>5} {r.deletions:>5} "
                   f"{r.insertions:>5}  {recall}")


@app.command()
def compare(
    job_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    runs: list[str] = typer.Argument(..., help="Two or more run ids, e.g. r1 r3."),
    samples: int = typer.Option(4, "--samples", help="Number of side-by-side passages."),
    window: float = typer.Option(30.0, "--window", help="Length of each passage (s)."),
) -> None:
    """Compare STT runs of one lecture: numbers + side-by-side passages."""
    from . import config as cfgmod
    from .evaluate import hypothesis_text, run_stats
    from .job import Job
    from .util import fmt_ts

    conf = cfgmod.load_config()
    job = Job(job_dir)
    stats = [run_stats(job, conf, r) for r in runs]
    typer.echo(f"{'run':<5} {'provider':<9} {'audio':>7} {'words':>7} {'repaired':>9} {'lost':>5} "
               f"{'low-conf':>9} {'STT time':>9}")
    for st in stats:
        stt = f"{st['stt_minutes']:.1f} min" if st["stt_minutes"] else "–"
        typer.echo(f"{st['run']:<5} {st['provider']:<9} {st['audio_min']:>5.1f} m {st['words']:>7} "
                   f"{st['repaired_min']:>7.1f} m {st['still_lost']:>5} {st['low_conf_pct']:>8.1f}% {stt:>9}")
    start = max(min(s["segments_list"][0]["start"] for s in stats if s["segments_list"]), 0.0)
    end = min(max(s["segments_list"][-1]["end"] for s in stats if s["segments_list"]), 1e9)
    for i in range(samples):
        a = start + (end - start - window) * (i + 0.5) / samples
        typer.secho(f"\n── {fmt_ts(a)}–{fmt_ts(a + window)} ──", bold=True)
        for st in stats:
            typer.echo(f"[{st['run']} {st['provider']}] {hypothesis_text(st['segments_list'], a, a + window)}")


# --- queue, worker, status (Phase 6) ---------------------------------------------------------

queue_app = typer.Typer(help="The machine-wide lecture queue (processed by `lecture worker`).", no_args_is_help=True)
app.add_typer(queue_app, name="queue")


@queue_app.command("add")
def queue_add(
    media: list[Path] = typer.Argument(..., exists=True, dir_okay=False, help="One or more lecture videos."),
    course: str = typer.Option(..., "--course", "-c", help="Course id from courses.yaml."),
    slides: list[Path] = typer.Option(None, "--slides", "-s", exists=True, dir_okay=False,
                                      help="Slide file(s) for these lectures (repeat for several)."),
    title: str = typer.Option(None, "--title", help="Title (only with one video; default: file name)."),
    date: str = typer.Option(None, "--date", help="YYYY-MM-DD (default: today)."),
    notes: str = typer.Option("never", "--notes", help="When to make notes: now | tonight | never."),
) -> None:
    """Queue lectures; the worker transcribes them one by one and makes notes when allowed."""
    from . import config as cfgmod
    from .queue import Queue, worker_running

    if title and len(media) > 1:
        raise typer.BadParameter("--title only works with a single video")
    known = {c.id for c in cfgmod.load_courses()}
    if course not in known:
        raise typer.BadParameter(f"unknown course {course!r}; known: {', '.join(sorted(known))}", param_hint="--course")
    queue = Queue()
    for m in media:
        item = queue.add(m, course, slides, title, date, notes)
        typer.echo(f"queued {item['id']}  {m.name}  (notes: {notes})")
    if not worker_running():
        typer.secho("No worker is running: start one with `lecture worker` (or the systemd service).", fg="yellow")


@queue_app.command("list")
def queue_list() -> None:
    """Show the queue with each lecture's status and current stage."""
    from .queue import Queue

    snap = Queue().snapshot()
    if not snap["items"]:
        typer.echo("Queue is empty.")
    for i in snap["items"]:
        stage = f" {i['stage']}" if i.get("stage") and i["status"] in ("transcribing", "notes") else ""
        pct = f" {100 * i['progress']:.0f}%" if i.get("progress") is not None and stage else ""
        extra = i.get("error") or (f"waits until {i['resume_at']}" if i.get("resume_at") else i.get("message") or "")
        typer.echo(f"{i['id']}  {i['status']:<13}{stage}{pct}  {Path(i['media']).name}  [notes {i['notes']}]"
                   + (f"\n          {extra[:150]}" if extra else ""))
    if snap["notes_paused"]:
        typer.secho("Notes are paused (lecture queue resume).", fg="yellow")


@queue_app.command("pause")
def queue_pause() -> None:
    """Pause note generation (transcription goes on)."""
    from .queue import Queue

    Queue().set_notes_paused(True)
    typer.echo("Notes paused.")


@queue_app.command("resume")
def queue_resume() -> None:
    """Resume note generation."""
    from .queue import Queue

    Queue().set_notes_paused(False)
    typer.echo("Notes resumed.")


@queue_app.command("retry")
def queue_retry(item_id: str = typer.Argument(..., help="Item id from `lecture queue list`.")) -> None:
    """Retry a failed (or waiting) item from where it stopped."""
    from .queue import Queue

    try:
        Queue().retry(item_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from None
    typer.echo(f"{item_id} queued again.")


@queue_app.command("remove")
def queue_remove(item_id: str = typer.Argument(..., help="Item id from `lecture queue list`.")) -> None:
    """Remove an item from the queue (its job folder and outputs stay)."""
    from .queue import Queue

    try:
        Queue().remove(item_id)
    except KeyError as exc:
        raise typer.BadParameter(str(exc)) from None
    typer.echo(f"{item_id} removed.")


@app.command()
def worker(
    once: bool = typer.Option(False, "--once", help="Stop when nothing can run right now."),
    idle: float = typer.Option(30.0, "--idle", help="Seconds between queue checks when idle."),
) -> None:
    """Process the queue (normally run by the lecture-worker systemd user service)."""
    from . import config as cfgmod
    from .queue import WorkerRunning, work

    try:
        work(cfgmod.load_config(), once=once, idle_s=idle)
    except WorkerRunning as exc:
        typer.secho(str(exc), fg="yellow")
        raise typer.Exit(4) from None
    except KeyboardInterrupt:
        typer.echo("\nWorker stopped; unfinished work resumes on the next start.")
        raise typer.Exit(130) from None


@app.command()
def status() -> None:
    """Worker, queue, GPU and quota usage at a glance."""
    from . import config as cfgmod
    from .status import gather, text

    for line in text(gather(cfgmod.load_config())):
        typer.echo(line)


@app.command()
def ui(
    port: int = typer.Option(7861, "--port", help="Local port (the UI only listens on 127.0.0.1)."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open a browser tab."),
) -> None:
    """Open the web UI (if it already runs, just opens the tab)."""
    from .ui import serve

    serve(port, browser=not no_browser)


@app.command("setup-simple")
def setup_simple(
    folder: Path = typer.Argument(..., help="Folder for the lectures (jobs and inbox go inside)."),
) -> None:
    """Set up simple mode for a new user (run by the Windows installer)."""
    from .settings import setup_simple as run

    run(folder)
    typer.echo(f"Simple mode set up; lectures in {folder}")


@app.command("app")
def app_command(
    port: int = typer.Option(7861, "--port", help="Local port (the UI only listens on 127.0.0.1)."),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open a browser tab."),
) -> None:
    """Verbatim as one program: UI + worker in this process, with a tray icon (Windows, macOS)."""
    from .app import run

    run(port, browser=not no_browser)


if __name__ == "__main__":  # `python -m lecture.cli …` (the UI starts the worker this way)
    app()
