---
name: latex-notes
description: Turn a recorded lecture (transcript + PDF/PPTX slides) into complete LaTeX lecture notes in the style of good handwritten course notes, one file per lecture in a course document, compiled to PDF when Tectonic is installed. Use when the user asks for LaTeX notes, lesnotities, "notes in latex" or a .tex of a lecture, from a Verbatim lecture or from loose transcript and slide files.
argument-hint: [lecture: job folder or name, e.g. "Les 6 DEP" | transcript file + slide files]
model: claude-sonnet-5-5
effort: high
allowed-tools: Bash(uv run *) Bash(cd *) Bash(tectonic *) Bash(mkdir *) Bash(cp *) Bash(ls *) Bash(command -v *) Read Write Edit Glob Grep
---

# LaTeX lecture notes

Input: $ARGUMENTS

Goal: notes a strong student would want to study from: as compact and visual as good handwritten notes,
but complete. Everything the lecturer explains, derives or works out goes in, including what is said but
not on the slides. Nothing invented: every statement comes from the transcript or the slides.

Skill folder: `~/.claude/skills/latex-notes` (scripts in `scripts/`, templates in `templates/`). This is a link to
`apps/verbatim/skill/latex-notes` in the Trivium repo: change it there.

**Started from Verbatim** (the input says so): nobody is there to answer, so never ask. Verbatim has already done
steps 1 and 2: the work folder, course folder, `main.tex` and the `\\input` line exist, and the lecture file is
named in the input. Go straight to step 3 and write that file; the lecture number is given too. End with the
report of step 6.

## 1. Find the material

- **Verbatim lecture**: a folder in `~/Lectures/jobs/` (match the user's words against the folder
  names: date, course, title; ask if two match). Use its transcript; it is already split into parts and
  matched to slides.
- **Loose files**: a transcript (.txt, .srt, .vtt, .md) and slides (.pdf, .pptx). Ask for the course name,
  lecture number/title, date and language if you can't tell from the files.

Run, with WORK = `<course folder>/.work/<lecture file name>/` (see step 2 for the names):
```
uv run ~/.claude/skills/latex-notes/scripts/prepare.py --job <job folder> --out WORK
uv run ~/.claude/skills/latex-notes/scripts/prepare.py --transcript <file> --slides <pdf/pptx> [--slides …] --out WORK
```
It writes `WORK/parts.md` (per part: time range, slide pages, slide text, transcript with [m:ss] stamps),
`WORK/lecture.json` (course, title, date, language, lecturer, slide files, page sizes) and slide previews in
`WORK/slides/`; with several decks, pages read "d2 p56" and previews `d2_p056.png`, and the top of `parts.md` says
which deck is which. Read all of `parts.md` (in chunks if it is long) before writing anything.
A part marked "slide match uncertain" may sit next to the wrong slide: trust the transcript.

## 2. Course folder

`~/Documents/Lesnotities/<Course name>/` (the course's full name, e.g. "Digitale elektronica en processoren";
for an app lecture take the name from `~/.config/lecture-transcriber/courses.yaml`, id = `course_id`).
```
main.tex              course document; \input's every lecture, sorted by date
lesnotities.sty       copied from templates/ (don't edit it per lecture)
lessen/<date>_<slug>.tex   one file per lecture, e.g. lessen/2026-03-05_les-6.tex
slides/<pdf>          copy of each slide PDF used for figure crops
figures/              pictures from PPTX files, TikZ is inline
.work/                prepare.py output (may be deleted afterwards)
```
New course: create the folder, copy `templates/lesnotities.sty`, and fill `templates/main.tex`
(%%COURSE%% = course name, %%SUBTITLE%% = "Lesnotities" / "Lecture notes", %%AUTHOR%% = the lecturer(s) or
empty, %%YEAR%% = academic year like 2025–2026, %%LANG%% = nl or en). Existing course: never overwrite
main.tex or other lectures; only add/replace this lecture's file and its \input line.
Add `\input{lessen/<file>}` between `% LESSEN BEGIN` and `% LESSEN END`, keeping the lines sorted by date.

## 3. Write the lecture file

Language: the lecture's language (lecture.json `language`); keep technical terms in the language the
lecturer uses for them (English terms in a Dutch lecture stay English).

Start with `\les{<number>}{<main subject of the lecture>}{<date written out>}`.

**Structure per topic, not per slide.** Follow the lecture's line of thought: `\onderwerp{…}` per topic
(several parts/slides on one subject = one topic), `\subsubsection*{…}` inside when useful. Put
`\slide{<page>}{<m:ss>}` at the start of each topic (and wherever the lecture jumps to another slide that
matters), so the reader can find the slide and the moment in the recording. With several decks: `\\slide{d2 p56}{…}`.

**Style of good handwritten notes**, in LaTeX:
- Short phrases and keywords instead of full paragraphs; full sentences only where an explanation needs it.
- Logic as arrows: `\pijl` (leads to, so), `\dus` (therefore), `$\Leftrightarrow$`; one step per line.
- Derivations written out step by step in `align*`, every step the lecturer does (and the obvious missing
  one), with `\opm{…}` grey remarks saying what happens in a step (`\opm{substitueer $u=RC$}`).
- `\opm{…}` also for the small asides next to a line: names of equations, units, "zie oefenzitting".
- Comparisons side by side: `\begin{vergelijk} … \tcblower … \end{vergelijk}` (dashed line between).
- Context, history, "in the real world", tangents: `\begin{kader}[Title] … \end{kader}` (dashed box).
- Key results the lecture builds towards: `\begin{formule} $…$ \end{formule}`.
- `stelling`, `bewijs`, `voorbeeld[title]`, `definitie` environments for those; worked examples from the
  lecture go in `voorbeeld` with all numbers and units.
- `\belangrijk` (orange star in the margin) where the lecturer says it's important, will be on the exam,
  or repeats it; also mention "examen" in an \opm if they said so.
- SI units with siunitx (`\qty{2}{\nano\second}`, `\unit{\micro\farad}`), units in every numeric result.
- Lists with `itemize` (dash bullets are the default); numbered steps with `enumerate`.

**Content rules**
- Complete: every concept, formula, example, trick, warning and exam hint from the lecture. What is only
  on a slide and not discussed: add it briefly, marked `\opm{alleen op de slide}`; `parts.md` has those slides'
  text at the end. A part with no slide at all is still lecture content: write it from the transcript.
- Correct: check every formula against the slide text; the transcript has speech-to-text errors (a
  misheard term, a dropped "niet"). When slide and transcript disagree, follow the slide and fix obvious
  transcription errors silently. When you can't tell, write the most likely version and add
  `% CHECK: <what and why>` on that line in the .tex.
- No filler: no "in deze les zagen we", no greetings, no admin (exam dates, room changes) unless the
  lecturer ties it to the content; organisational exam info goes in one `kader` at the end if present.
- Never invent results, numbers or explanations that are not in the material.

## 4. Figures

Look at the previews in `WORK/slides/` for the slides of each topic (p162.png = slide page 162).
- **Real figures** (circuits, layouts, measured plots, photos, complex diagrams): crop them from the PDF as
  a vector image. Copy the PDF to `<course>/slides/` once, then read the box off the preview as fractions
  of the page (0,0 = top left) and run
  `uv run ~/.claude/skills/latex-notes/scripts/crop.py <course>/slides/<pdf> <page> X0 Y0 X1 Y1 --preview WORK/crop.png`.
  Look at the preview; adjust until only the figure (with its labels) is in it. Use the printed
  `\includegraphics` line inside `\begin{center} … \end{center}`, or `\slidefig{width}{page}{trim}{slides/<pdf>}{caption}`.
- **Simple sketches** (axes with a curve, potential wells, energy levels, timing diagrams, block diagrams,
  a small gate network): redraw in TikZ / pgfplots / circuitikz, small and clean, like a hand sketch.
- PPTX: there are no page previews, only the pictures in the deck, extracted to `WORK/slides/<file>_sNNN_k.<ext>`
  (sNNN = slide). Look at them, copy the ones you need to `<course>/figures/` and include them. Shapes drawn in
  PowerPoint are not in there: redraw those in TikZ when they matter.
- At most one figure per idea; no decorative pictures, logos or photos of the lecturer.

## 5. Compile and check

If `command -v tectonic` finds it: `cd <course folder> && tectonic main.tex` (the first run downloads
packages, which can take a minute). A bad line in an older lecture of the course stops the whole document: then
fix that line minimally and say so in the report. Fix every error and rerun until it compiles; then look at the warnings
for overfull lines in your file and fix the bad ones. If Tectonic is missing, don't install anything: tell
the user `sudo pacman -S tectonic` and that the .tex is ready.

Then reread your lecture file once against `parts.md`, part by part: is every part covered, every
formula checked, every `% CHECK` still needed?

## 6. Report (short)

- Paths: the lecture file, main.tex, the PDF (if compiled) and its page count.
- Topics covered (one line), number of figures (cropped / TikZ).
- Every `% CHECK` with its line, and parts of the recording you couldn't follow (garbled transcript).
