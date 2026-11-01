"""Stage 8: review.md — everything worth double-checking in this lecture's outputs, in one place."""

from __future__ import annotations

from collections import Counter

from ..job import Job
from ..util import fmt_ts, read_json


def _segments_flagged(segments: list[dict], flag: str) -> list[dict]:
    return [s for s in segments if flag in s.get("flags", [])]


def render(job: Job, heading: str) -> str:
    st = job.manifest["stages"]
    out = [f"# Review: {heading}", "",
           "What to double-check, with timestamps. Generated; rerun `lecture resume` to refresh.", ""]

    # transcription
    run_id = job.current_run
    info = job.run_info(run_id) if run_id else {}
    out += ["## Transcription", ""]
    if run_id:
        out.append(f"- Run {run_id}, speech-to-text: {info.get('provider') or 'groq'}"
                   + (", with slide term prompt" if info.get("term_prompt") else ""))
    tr_path = job.root / "transcript_raw.json"
    if tr_path.exists():
        tr = read_json(tr_path)
        segs = tr["segments"]
        skipped = tr.get("skipped", [])
        if skipped:
            out.append("- Long silences skipped (not transcribed): "
                       + ", ".join(f"{fmt_ts(a)}–{fmt_ts(b)}" for a, b in skipped))
        unrepaired = st.get("transcribe", {}).get("unrepaired", [])
        if unrepaired:
            out.append("- **Speech that could not be transcribed** (Whisper stuck, retry failed): "
                       + ", ".join(f"{fmt_ts(a)}–{fmt_ts(b)}" for a, b in unrepaired))
        fixed = tr.get("fixes", [])
        if fixed:
            out.append("- Words fixed (course fix list / sound-alike of a slide keyword): " + ", ".join(
                f"{f['from']} → {f['to']} ({f['count']}×{', auto' if f['kind'] == 'auto' else ''})" for f in fixed))
        removed = Counter(r["reason"] for r in tr.get("removed", []))
        if removed:
            out.append("- Removed by the filters: " + ", ".join(f"{n}× {k}" for k, n in removed.most_common()))
            masked = [r for r in tr["removed"] if r["reason"] == "masked"]
            if masked:
                out.append("- **No transcript ('***') at**: " + ", ".join(fmt_ts(r["start"]) for r in masked[:20]))
        low = _segments_flagged(segs, "low_confidence")
        if low:
            out.append(f"- Low-confidence lines ({len(low)}): " + ", ".join(fmt_ts(s["start"]) for s in low[:20])
                       + (" …" if len(low) > 20 else ""))
        repaired = _segments_flagged(segs, "repaired")
        if repaired:
            out.append(f"- Re-transcribed stretches ({len(repaired)}): "
                       + ", ".join(fmt_ts(s["start"]) for s in repaired[:20]))
    out.append("")

    # sections
    sec_path = job.root / "sections.json"
    if sec_path.exists():
        sec = read_json(sec_path)
        out += ["## Slide sections", ""]
        if sec["method"] == "pauses":
            out.append("- No slides: sections every few minutes at pauses (titles come from the notes).")
        uncertain = [s for s in sec["sections"] if s.get("low_confidence")]
        if uncertain:
            out.append("- Uncertain slide ↔ transcript match: "
                       + "; ".join(f"{s['index']}. {s['title']} at {fmt_ts(s['start'])}" for s in uncertain))
        if sec["slides_not_discussed"]:
            out.append(f"- Slides never matched to the transcript ({len(sec['slides_not_discussed'])}; maybe "
                       "skipped, maybe just not recognised): "
                       + ", ".join(str(s["page"]) for s in sec["slides_not_discussed"]))
        out.append("")

    # notes
    notes_dir = job.root / "notes"
    batches = sorted(notes_dir.glob("batch_*.json")) if notes_dir.exists() else []
    notes_stage = st.get("notes", {})
    out += ["## Notes", ""]
    if notes_stage.get("status") == "pending":
        out.append(f"- **Not made yet**: {notes_stage.get('reason', '')}")
    elif not batches:
        out.append("- Not made yet (`lecture notes <job>`). `outputs/study_pack.md` works by hand meanwhile.")
    for path in batches:
        b = read_json(path)
        att = [a for a in b.get("attempts", []) if "model" in a]
        tokens = (f"{sum(a['input_tokens'] for a in att):,} in / {sum(a['output_tokens'] for a in att):,} out tokens, "
                  f"{sum(a['elapsed_s'] for a in att):.0f} s") if att else ""
        out.append(f"- Sections {b['sections'][0]}–{b['sections'][-1]}: {b['provider']} ({b['model']}), "
                   f"{len(b.get('attempts', []))} attempt(s){', ' + tokens if tokens else ''}")
        for flag in b.get("flags", []):
            out.append(f"  - **{flag}**")
        for d in b.get("dropped", []):
            out.append(f"  - Bullet removed (timestamp outside its section): {d}")
    out.append("")
    return "\n".join(out)
