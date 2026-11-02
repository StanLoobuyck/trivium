---
name: latex-notes
description: Turn a recorded lecture (transcript + PDF/PPTX slides) into complete LaTeX lecture notes in the style of good handwritten course notes, one file per lecture in a course document, compiled to PDF when Tectonic is installed. Use when the user asks for LaTeX notes, lesnotities, "notes in latex" or a .tex of a lecture, from a Verbatim lecture or from loose transcript and slide files.
argument-hint: [lecture: job folder or name, e.g. "Les 6 DEP" | transcript file + slide files]
model: claude-opus-5-5
effort: high
allowed-tools: Bash(uv run *) Bash(tectonic *) Bash(mkdir *) Bash(cp *) Bash(ls *) Bash(command -v *) Read Write Edit Glob Grep
---

# LaTeX lecture notes

Input: $ARGUMENTS

Goal: notes a strong student would want to study from: as compact and visual as good handwritten notes,
and complete in information. Every fact, formula, derivation idea, example and warning goes in, including
what is said but not on the slides; the words around them are what gets squeezed (see Density).
Nothing invented: every statement comes from the transcript or the slides.

`<skill>` below = the folder this SKILL.md is in (scripts in `scripts/`, templates in `templates/`). The source is
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
uv run <skill>/scripts/prepare.py --job <job folder> --out WORK
uv run <skill>/scripts/prepare.py --transcript <file> --slides <pdf/pptx> [--slides …] --out WORK
```
It writes `WORK/parts.md` (per part: time range, slide pages, slide text, transcript with [m:ss] stamps),
`WORK/lecture.json` (course, title, date, language, lecturer, slide files, page sizes) and slide previews in
`WORK/slides/`; with several decks, pages read "d2 p56" and previews `d2_p056.png`, and the top of `parts.md` says
which deck is which. Read all of `parts.md` (in chunks if it is long) before writing anything.
A part marked "slide match uncertain" may sit next to the wrong slide: trust the transcript. Several very short
uncertain parts in a row mean the match failed there: read what is really said and take the topic from that. The
transcript sets the order and the subject of the notes; slide order and part titles don't.

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

Language: the lecture's language (lecture.json `language`), also for the standard remarks: the Dutch `\opm{…}`
wordings here become English in an English lecture (`\opm{only on the slide}`, `\opm{work out}`). Keep technical terms in the language the
lecturer uses for them (English terms in a Dutch lecture stay English).

Start with `\les{<number>}{<main subject of the lecture>}{<date written out>}`.

**Structure per topic, not per slide.** Follow the lecture's line of thought: `\onderwerp{…}` per topic
(several parts/slides on one subject = one topic), `\subsubsection*{…}` inside when useful. Put
`\slide{<page>}{<m:ss>}` at the start of each topic (and wherever the lecture jumps to another slide that
matters), so the reader can find the slide and the moment in the recording. The moment is when the transcript
really says it, so moments only go forward; a topic that isn't in the transcript gets `\slide{<page>}{}`, no time.
Write `\slide` straight after its heading. No own `\newcommand` or `\setlength` in the lecture file: `\tijd{<m:ss>}` in
the margin and the rest are in `lesnotities.sty`. With several decks: `\\slide{d2 p56}{…}`.

**Style of good handwritten notes**, in LaTeX:
- Short phrases and keywords instead of full paragraphs; full sentences only where an explanation needs it.
- Logic as arrows: `\pijl` (leads to, so), `\dus` (therefore), `$\Leftrightarrow$`; one step per line.
- Derivations in `align*`, one line per non-trivial step the lecturer takes, with `\opm{…}` grey remarks
  saying what happens (`\opm{substitueer $u=RC$}`). Pure bookkeeping (expanding, collecting terms) is one
  line with `\opm{uitwerken}`; never skip a step where something is substituted, approximated or assumed.
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
- Complete: every concept, formula, example, trick, warning and exam hint from the lecture. A part with no
  slide at all is still lecture content: write it from the transcript.
- What is only on a slide (`parts.md` has those slides' text at the end, and a "discussed" slide can be a wrong match):
  at most one line per slide, together in one last topic `\onderwerp{Alleen op de slides}`, never between what was
  said. In a lecture in parts ("deel 3") those slides are often the subject of another part: keep only what fits this one.
- Correct: check every formula against the slide text; the transcript has speech-to-text errors (a
  misheard term, a dropped "niet"). When slide and transcript disagree, follow the slide and fix obvious
  transcription errors silently. When you can't tell, write the most likely version and add
  `% CHECK: <what and why>` on that line in the .tex.
- No filler: no "in deze les zagen we", no greetings, no admin (exam dates, room changes) unless the
  lecturer ties it to the content; organisational exam info goes in one `kader` at the end if present.
- Never invent results, numbers or explanations that are not in the material.

**Density**: compress words, never information. The notes must stay short enough to review.
- Budget: about 5 pages per hour of recording (recording length = last time stamp in `parts.md`; a 2 h
  lecture ≈ 10 pages). Derivation- or figure-heavy lectures may run ~20% over, talk-heavy ones should come
  in well under, and any recording may take 3. It is a ceiling, not a target to fill. Figures and circuits the
  lecture works with stay: cut words first.
- Write each idea once. Where the lecturer repeats, rephrases or recaps, keep the clearest version (and
  `\belangrijk` if the repetition signals importance). Slide text the lecturer only reads out is not
  written twice.
- One line per idea: keyword or short phrase plus formula. No "de lector legt uit dat…".
- When something is too long, cut in this order: (1) repetition and recaps, (2) anecdotes and motivation →
  one line, or a `kader` of at most 3 lines, (3) routine algebra and arithmetic → result plus `\opm`,
  (4) prose that duplicates a formula or figure, (5) a figure that adds nothing beyond a formula.
- Never cut: definitions, formulas with their conditions, results, worked-example numbers, warnings and
  pitfalls, exam hints, and the reason behind a non-obvious step.
- Use compact forms: `vergelijk` for two-sided comparisons, one `align*` per derivation, `\pijl` chains,
  small TikZ instead of a large crop. No manual vertical space (`\\[…]`, `\bigskip`, blank-line stacks).

## 4. Figures

Look at the previews in `WORK/slides/` for the slides of each topic (p162.png = slide page 162).
- **Real figures** (circuits, layouts, measured plots, photos, complex diagrams): crop them from the PDF as
  a vector image. Copy the PDF to `<course>/slides/` once, then read the box off the preview as fractions
  of the page (0,0 = top left) and run
  `uv run <skill>/scripts/crop.py <course>/slides/<pdf> <page> X0 Y0 X1 Y1 --preview WORK/crop.png`.
  Look at the preview; adjust until only the figure (with its labels) is in it, at most 3 tries per figure.
  Still wrong: redraw it in TikZ, or keep the best crop with a `% CHECK`. Use the printed
  `\includegraphics` line inside `\begin{center} … \end{center}`, or `\slidefig{width}{page}{trim}{slides/<pdf>}{caption}`.
- **Simple sketches** (axes with a curve, potential wells, energy levels, timing diagrams, block diagrams,
  a small gate network): redraw in TikZ / pgfplots / circuitikz, small and clean, like a hand sketch.
- PPTX: there are no page previews, only the pictures in the deck, extracted to `WORK/slides/<file>_sNNN_k.<ext>`
  (sNNN = slide). Look at them, copy the ones you need to `<course>/figures/` and include them. Shapes drawn in
  PowerPoint are not in there: redraw those in TikZ when they matter.
- At most one figure per idea; no decorative pictures, logos or photos of the lecturer.

## 5. Compile and check

If `command -v tectonic` finds it: `tectonic "<course folder>/main.tex"` (the PDF lands next to it; the first run downloads
packages, which can take a minute). A bad line in an older lecture of the course stops the whole document: then
fix that line minimally and say so in the report. Fix every error and rerun until it compiles; then look at the warnings
for overfull lines in your file and fix the bad ones. If Tectonic is missing, don't install anything: tell
the user `sudo pacman -S tectonic` and that the .tex is ready.

Page budget: this lecture's pages = pages of `main.pdf` now minus before you added it (new course: minus
the title page; Verbatim gives the number before in the input). Count with
`uv run --with pypdf python -c "import pypdf;print(len(pypdf.PdfReader('<course folder>/main.pdf').pages))"`.

Then run `uv run <skill>/scripts/check.py <lecture file> WORK --pages <N>` and fix everything it prints: wrong moments,
own macros. Over budget: do one compression pass on the .tex (tighten wording, merge, remove duplication; delete no
facts), recompile, recount and rerun the check. Only one pass; if still over, leave it and report the numbers.
Look at two rendered pages of this lecture too (`uv run --with pymupdf python -c "import pymupdf;pymupdf.open('<pdf>')[<n>].get_pixmap(dpi=80).save('WORK/page.png')"`,
then Read the PNG): text running into the margin, a figure that is too large, a broken box.

Then reread your lecture file once against `parts.md`, part by part: is every part covered, every
formula checked, every `% CHECK` still needed? After a compression pass this also confirms nothing
was lost.

## 6. Report (short)

- Paths: the lecture file, main.tex, the PDF (if compiled), and this lecture's pages against the budget
  (e.g. "9 pages, budget 10").
- Topics covered (one line), number of figures (cropped / TikZ).
- The last line of `check.py`. Every `% CHECK` with its line, and parts of the recording you couldn't follow (garbled transcript).
