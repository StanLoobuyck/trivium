"""Prepare a reference stretch for the user to correct by hand (Phase 1 open item, needed for 8.6/8.7).

    uv run python scripts/make_reference.py JOB_DIR START END NAME [--out ~/Lectures/references]

Writes <out>/<NAME>.mp3 (the stretch, to listen to) and <out>/<NAME>.txt (the main transcript of that
stretch, one sentence per line, a '# mm:ss' comment every ~30 s), and adds the entry to <out>/refs.yaml so
`lecture eval ~/Lectures/references/refs.yaml --run rN` scores every run against all references.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import yaml

from lecture import config as cfgmod
from lecture.evaluate import job_segments
from lecture.job import Job
from lecture.subtitles import timed_tokens
from lecture.util import fmt_ts, parse_ts

HEADER = """# Reference: {name} ({job}, {start}–{end})
# Listen to {name}.mp3 and make this text say EXACTLY what is said: fix wrong words and spelling (terms as on
# the slides), add missed words, remove words that weren't said. Keep 'eh'/'uhm' out. Lines starting with '#'
# are ignored (the times help you find your place: they count from the start of the mp3).
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("start")
    ap.add_argument("end")
    ap.add_argument("name")
    ap.add_argument("--out", type=Path, default=Path.home() / "Lectures" / "references")
    args = ap.parse_args()
    job, conf = Job(args.job), cfgmod.load_config()
    a, b = parse_ts(args.start), parse_ts(args.end)
    args.out.mkdir(parents=True, exist_ok=True)

    words = [(t, (s + e) / 2) for seg in job_segments(job, conf, None) for t, s, e in timed_tokens(seg)]
    words = [(t, m) for t, m in words if a <= m <= b]
    lines, current, next_mark = [], [], a
    for token, mid in words:
        if mid >= next_mark and not current:
            lines.append(f"# {fmt_ts(mid - a)}")
            next_mark = mid + 30
        current.append(token)
        if re.search(r"[.!?]$", token):
            lines.append(" ".join(current))
            current = []
    if current:
        lines.append(" ".join(current))
    txt = args.out / f"{args.name}.txt"
    if txt.exists():
        raise SystemExit(f"{txt} exists (maybe already corrected): not overwritten")
    txt.write_text(HEADER.format(name=args.name, job=job.root.name, start=args.start, end=args.end)
                   + "\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", str(job.full_audio),
                    "-c:a", "libmp3lame", "-q:a", "4", str(args.out / f"{args.name}.mp3")], check=True)

    index = args.out / "refs.yaml"
    items = yaml.safe_load(index.read_text()) if index.exists() else []
    items = [i for i in items if i["ref"] != txt.name] + [
        {"ref": txt.name, "job": str(job.root), "start": args.start, "end": args.end}]
    index.write_text(yaml.safe_dump(items, sort_keys=False, allow_unicode=True))
    print(f"{txt} ({len(words)} words) + {args.name}.mp3")


if __name__ == "__main__":
    main()
