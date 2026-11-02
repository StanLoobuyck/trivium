# Verbatim (Lecture Transcriber)

Turns lecture recordings (MP4, often hundreds of MB) plus optional slides (PDF/PPTX) into a slide-aligned
transcript, subtitles and study notes. Transcription runs **locally on the NVIDIA GPU** (faster-whisper
large-v3), with Groq's free Whisper API as fallback. Notes will be written by Claude (`claude -p` on a Claude
Pro subscription) with Gemini as fallback.

Status: **Phase 2 started** (local Whisper works; transcripts + subtitles; notes not yet). The build plan
is in [PLAN.md](PLAN.md) — section 10 says what's next; progress and measurements in
[CHANGELOG.md](CHANGELOG.md).

## Usage

```bash
lecture run ~/Videos/Recordings/les05.mp4 --course algemene-economie --title "Les 5" --date 2026-10-14 \
    --slides ~/Downloads/les05.pdf          # optional, repeatable (used from Phase 3)
lecture resume ~/Lectures/jobs/2026-10-14_algemene-economie_les-5   # continue after a stop/crash
```

Running `lecture run` again on the same file and course resumes the existing job; finished chunks are
never sent to Groq again. Results land in `~/Lectures/jobs/<job>/outputs/`:
`transcript_raw.txt` (timestamped), `subtitles.srt` / `.vtt` (open the video in mpv/VLC with them) and
`transcript.md` (the transcript under a heading per slide, with its time range; add slides with
`--slides file.pdf`, also on an existing job — a multi-lecture PDF is narrowed to the outline section
named in the job title, e.g. "Les 4").

Everyday use: open **Verbatim** from the app launcher (Super+Space; searching "lecture" also finds it) or run `lecture ui`, add lectures (pick recent
recordings or drop files; slides; when to make notes: now / tonight / never) and close the browser — the background worker
does the rest and sends a notification per lecture. Per lecture you pick the course and the spoken language
(Dutch/English; defaults to the course's); a new course can be made right in the upload form. Your lectures
are grouped in tiles (one per course, plus your own folders); lectures, folders and courses can be renamed,
lectures deleted. Each lecture page plays the recording next to the notes; click any timestamp to jump there.
Light/dark follows the system (sun/moon button to override). Same from the terminal:
`lecture queue add VIDEO… -c COURSE [-s SLIDES.pdf] [--notes tonight]`, `lecture queue list`, `lecture status`.
The worker runs as a systemd user service (once: `systemctl --user enable --now lecture-worker.service`
after `scripts/install.sh`), or by hand with `lecture worker`.

Watch folder: move a downloaded recording into `~/Lectures/inbox/<course-id>/` (made for every current
course) and the worker queues it once it stops changing (30 s). Keep the course's slides in the same folder:
a deck with the same name or lecture number ("les 4", "HC 4", "week 4") is used; courses with a few big decks
get all of them (the slide alignment finds what was shown); a deck named "les 3-6" counts for each of those lectures. A numbered lecture whose own deck
isn't there yet waits 30 minutes and shows on the dashboard ("Add by hand" opens the Add page with the course filled
in), then gets all decks. A recording without a number never waits for a deck: it gets all of them.
Settings → Mac at home: the model server's address and token, with a connection test.

Study notes (uses your Claude subscription via `claude -p`, Gemini as fallback; one call of ~2 min per
2 h lecture): `lecture notes <job>` → `notes.md`, `summary.md`, `glossary.md`, `exam_hints.md`, `quiz.md`,
`flashcards_anki.csv` (Anki: File → Import). `lecture run` never calls an LLM; it always writes
`study_pack.md` (paste into a Claude Project to make notes by hand) and `review.md` (what to double-check).
`notes.schedule` / `notes.max_claude_calls_per_day` in config.yaml limit Claude use.

Misheard terms: after transcription, rare words that sound like a slide keyword are replaced (nent → NAND,
ELU → ALU; `fixes.py`), plus a fix list per course (`corrections:` in courses.yaml, or the Keywords tab of a
lecture / Setup → course). Every replacement is listed in the Quality check (`review.md`).
Then the worker asks a local LLM on the Mac (Ollama, `termfix.model`, default qwen3.8:27b) for more:
they appear in the lecture's **Suggestions** tab, where Accept changes only that spot (OR vs NOR depends on
the spot), Whole course adds it to the course fix list. Nothing changes by itself. By hand: `lecture suggest JOB`.

Speech-to-text: `stt.providers: [local, groq]` in `config.yaml`. Local (GPU) is used when available;
otherwise Groq, automatically. Each transcription run remembers its provider. Compare providers with
`lecture redo <job> --stage transcribe --provider local|groq [--range A-B]` and
`lecture compare <job> r1 r2`; make the run you prefer the main transcript with `lecture use <job> r2`.

Free-quota behaviour (Groq only): if Groq's hourly audio limit (2 h of audio per hour) is reached, the run waits and
continues automatically. If the daily limit (8 h of audio) is reached, it stops cleanly (exit code 3)
and tells you when to resume.

Exit codes: 0 done · 1 error · 3 paused for quota · 4 job already running · 130 interrupted.

### Measuring quality (`lecture eval`)

Make a reference transcript of ~5 min from the **middle** of a lecture: type exactly what is said,
no "euh"/"uhm", standard spelling, terms spelled as on the slides. Note where it starts and ends.

```bash
lecture eval ref_les05.txt ~/Lectures/jobs/<job> --start 00:41:00 --end 00:46:00
```

Reports word error rate (WER) and recall of course terms (`extra_terms` + lecturer). Several references
at once: a YAML file with entries `{ref: file.txt, job: path, start: "00:41:00", end: "00:46:00"}`.

Re-transcribe only a time range as a separate run (for noise measurements or experiments; the main
transcript stays as it is), then evaluate that run:

```bash
lecture redo <job> --stage transcribe --range 00:40:00-00:47:00 [--chunk-target 150]
lecture eval ref_les05.txt <job> --start 00:41:00 --end 00:46:00 --run r2
```

## Install (Arch Linux)

```bash
sudo pacman -S --needed ffmpeg uv libnotify     # required (NVIDIA driver for local transcription)
sudo pacman -S --needed libreoffice-fresh pandoc-cli   # optional: PPTX rendering, .docx/.pdf export
scripts/install.sh
```

`install.sh` pins Python 3.12 (downloaded by uv, the system Python is untouched), creates the project
venv with the `local` extra (faster-whisper + CUDA libraries as pip wheels — no system CUDA needed),
installs the `lecture` command into `~/.local/bin`, and creates `~/.config/lecture-transcriber/.env`
(mode 600). The Whisper model (~3 GB) downloads on first use.

## API keys

Paste them into `~/.config/lecture-transcriber/.env`:

| Key | Where | Note |
|---|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys | Whisper + fallback LLM |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey | Use a **personal** Google account; KU Leuven accounts often have AI Studio disabled |
| `OPENROUTER_API_KEY` | https://openrouter.ai/keys | Optional |

Then run:

```bash
lecture doctor            # checks everything; makes one tiny test call per provider
lecture doctor --no-calls # list models only (saves 1 Gemini request + 10 s Groq audio)
```

Gemini doesn't expose its free-tier quota via the API. Look it up once at
https://aistudio.google.com/rate-limit and put the real numbers in
`~/.config/lecture-transcriber/config.yaml`, e.g.:

```yaml
limits:
  gemini:
    requests_per_day: 250
```

## Configuration

- `config.yaml` (repo) — defaults: models, fallback chains, free-tier limits. Override any key in
  `~/.config/lecture-transcriber/config.yaml` (deep-merged; unknown keys are rejected to catch typos).
- `courses.yaml` (repo) — your courses. A `~/.config/lecture-transcriber/courses.yaml` replaces it.

## Privacy

Extracted audio chunks and transcript/slide text are sent to Groq and Google. For users in the
EEA, Google's Gemini API terms apply the paid-service data terms to free quota too (prompts aren't used
to improve Google's products; human review isn't explicitly excluded). Check KU Leuven's rules on
uploading recordings to third-party services, and keep in mind that questions from the room contain
other students' voices. Original video and slide files never leave your computer.

## Development

```bash
uv run pytest            # offline unit + integration tests (fake Groq)
LECTURE_LIVE_CLIP=clip.mp4 uv run pytest -m live   # real Groq call on a short clip
uv run lecture doctor    # run from the project venv
```
