"""Experiments 8.6 / 8.7a (PLAN.md Phase 8): side STT runs with other Whisper prompts, on the Mac.

    uv run python scripts/exp_prompts.py JOB_DIR VARIANT [--url URL] [--ollama URL] [--llm MODEL]

Variants (all repeat their prompt on every 30 s window = carry, see mac/server.py _install_carry):
  carry   the job's normal term prompt (terms.json), carried.                 vs main run: effect of carrying
  parts   per chunk: rule-based terms of the slides on screen in that chunk.  vs carry: per-part terms (8.7a)
  ollama  per chunk: an LLM's keywords from the same slides.                  vs parts: LLM vs rules (8.6)

parts/ollama take "slides on screen" from the main run's sections.json (a second pass). The side run reuses
the main run's chunk plan, never becomes the main transcript (`lecture use` does that), and resumes per chunk.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import httpx

from lecture import config as cfgmod
from lecture import pipeline
from lecture.job import Job
from lecture.providers.mac_whisper import MacWhisper
from lecture.cli import ConsoleReporter
from lecture.stages import s4_transcribe
from lecture.stages.s3_chunk import chunks_from_plan
from lecture.terms import build_term_list, build_whisper_prompt
from lecture.util import read_json

KEYWORD_PROMPT = """Hieronder staat de tekst van de slides die de docent toont tijdens een stuk van een les \
"{course}". Een spraakherkenner (Whisper) zal dit stuk uitschrijven en schrijft vaktermen vaak fout.
Geef de woorden die hij het meest waarschijnlijk verkeerd schrijft: vaktermen, afkortingen, eigennamen, \
Engelse termen, formules in woorden. Maximaal {n}, belangrijkste eerst, exact gespeld zoals op de slides. \
Geen gewone Nederlandse woorden, geen zinnen.
Antwoord alleen met JSON: {{"terms": ["...", "..."]}}

Slides:
{text}"""


def slides_by_chunk(job: Job, run_id: str) -> dict[int, list[dict]]:
    """Slides (slides.json entries) shown during each chunk, from the main run's sections."""
    slides = {(s["file"], int(s["page"])): s for s in read_json(job.slides_dir / "slides.json")["slides"]}
    sections = read_json(job.root / "sections.json")["sections"]
    out: dict[int, list[dict]] = {}
    for chunk in s4_transcribe.run_chunks(job, run_id):
        seen = []
        for sec in sections:
            if sec["end"] > chunk.keep_start and sec["start"] < chunk.keep_end:
                seen += [slides[(r["file"], int(r["page"]))] for r in sec["slides"] if (r["file"], int(r["page"])) in slides]
        out[chunk.id] = list({s["id"]: s for s in seen}.values())
    return out


def slide_text(s: dict) -> str:
    return f"{s.get('title') or ''}\n{s['text']}\n{s.get('notes') or ''}".strip()


def ollama_json(url: str, model: str, prompt: str) -> dict:
    """Chat with Ollama and parse the first JSON object of the answer. No `format`: the Homebrew build
    (0.40.6, MLX backend) lacks libollama_xgrammar, so structured output answers 501."""
    body = {"model": model, "stream": False, "think": False, "options": {"temperature": 0, "num_ctx": 16384},
            "messages": [{"role": "user", "content": prompt}]}
    r = httpx.post(f"{url}/api/chat", json=body, timeout=900)
    r.raise_for_status()
    text = r.json()["message"]["content"]
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{model}: no JSON in answer: {text[:200]!r}")
    return json.JSONDecoder().raw_decode(text[start:])[0]


def ollama_terms(url: str, model: str, course: str, slides: list[dict], n: int = 40) -> list[str]:
    terms = ollama_json(url, model, KEYWORD_PROMPT.format(
        course=course, n=n, text="\n\n---\n\n".join(slide_text(s) for s in slides)))["terms"]
    return list(dict.fromkeys(t.strip() for t in terms if t.strip()))[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("variant", choices=["carry", "parts", "ollama"])
    ap.add_argument("--url", default="http://my-mac:7863", help="experiment copy of the Mac server")
    ap.add_argument("--ollama", default="http://localhost:11435", help="Ollama (ssh -L 11435:localhost:11434 mac)")
    ap.add_argument("--llm", default="gemma4:12b")
    args = ap.parse_args()

    conf = cfgmod.load_config()
    conf.stt.mac.url = args.url
    rep = ConsoleReporter()
    job = Job(args.job)
    main_run = job.current_run
    label = args.variant if args.variant != "ollama" else f"ollama:{args.llm}"
    run_id = next((r for r, i in job.manifest["stt"]["runs"].items() if i.get("experiment") == label), None)
    if run_id is None:
        course = pipeline.job_course(job)
        info: dict = {"term_prompt": pipeline.term_prompt(job), "carry_prompt": True}
        if args.variant in ("parts", "ollama"):
            shown = slides_by_chunk(job, main_run)
            lecturer = [{"term": course.lecturer, "source": "lecturer"}] if course.lecturer else []
            prompts, keywords = {}, {}
            for cid, slides in shown.items():
                if not slides:
                    continue  # nothing on screen known: the run's normal term prompt
                if args.variant == "parts":
                    terms = build_term_list([slide_text(s) for s in slides], [], course, conf)
                else:
                    words = ollama_terms(args.ollama, args.llm, course.name, slides)
                    keywords[str(cid)] = words
                    terms = lecturer + [{"term": w, "source": "llm"} for w in words]
                prompts[str(cid)] = build_whisper_prompt(terms, course, conf.terms.prompt_max_tokens)
                rep.info(f"chunk {cid}: {len(slides)} slides → {prompts[str(cid)][:150]}…")
            info.update(chunk_prompts=prompts, **({"llm_keywords": keywords} if keywords else {}))
        run_id = job.new_run(False, target_s=job.run_info(main_run)["target_s"], provider="mac",
                             audio_hash=job.run_info(main_run).get("audio_hash"), range=None, chunk_ids=None,
                             experiment=label, **info)
        job.run_dir(run_id).mkdir(parents=True, exist_ok=True)
        shutil.copy(job.run_dir(main_run) / "chunks.json", job.run_dir(run_id) / "chunks.json")
    rep.info(f"Run {run_id} ({label}) of {job.root.name}")
    token = cfgmod.load_keys()["LECTURE_MAC_TOKEN"]
    stt = MacWhisper(conf, token, rep)
    stt.check()
    s4_transcribe.transcribe_run(job, conf, run_id, stt, rep)
    lost = s4_transcribe.repair_run(job, conf, run_id, stt, rep)
    n = len(chunks_from_plan(read_json(job.run_dir(run_id) / "chunks.json")))
    rep.info(f"Done: {run_id}, {n} chunks, {len(lost)} stretches still lost")
    print(run_id)


if __name__ == "__main__":
    sys.exit(main())
