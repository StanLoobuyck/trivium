"""Phase 8.7 experiment: other speech models on the Mac (mlx-audio) on one chunk, same input as Whisper.

Runs in its own venv (~/asr-bench, `uv add mlx-audio`), not the model server's.
    uv run python bench_asr.py VARIANT data/chunk5.flac data/terms.json data/slides_chunk5.txt out/
VARIANT: qwen | qwen-hotwords | qwen-context | parakeet | cohere
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import mlx.core as mx
from mlx_audio.stt.utils import load

MODELS = {
    "qwen": "mlx-community/Qwen3-ASR-1.7B-8bit",
    "parakeet": "mlx-community/parakeet-tdt-0.6b-v3",
    "cohere": "CohereLabs/cohere-transcribe-03-2026",
}


def clean_slides(text: str) -> str:
    """Slide text as context: drop truth-table digits, single symbols and duplicate lines."""
    seen, out = set(), []
    for line in text.splitlines():
        line = line.strip(" ❑➢•-")
        if len(line) < 3 or re.fullmatch(r"[\d\s.,:;=+()\-]+", line) or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return "\n".join(out)


def main() -> None:
    variant, clip, terms_f, slides_f, out_dir = sys.argv[1:6]
    info = json.loads(Path(terms_f).read_text())
    family = variant.split("-")[0]
    t0 = time.perf_counter()
    model = load(MODELS[family])
    load_s = time.perf_counter() - t0
    kwargs: dict = {}
    if family == "qwen":
        kwargs["language"] = "Dutch"
        if variant == "qwen-hotwords":
            kwargs["hotwords"] = info["terms"]
        if variant == "qwen-context":
            kwargs["system_prompt"] = ("Hoorcollege Digitale elektronica en processoren (KU Leuven), docent Ada "
                                       "Example. Vaktermen: " + ", ".join(info["terms"]) +
                                       ".\nTekst op de slides:\n" + clean_slides(Path(slides_f).read_text()))
    elif family == "cohere":
        kwargs["language"] = "nl"
    mx.reset_peak_memory()
    t0 = time.perf_counter()
    result = model.generate(clip, **kwargs)
    wall = time.perf_counter() - t0
    text = getattr(result, "text", None) or str(result)
    segs = getattr(result, "segments", None) or getattr(result, "sentences", None) or []
    has_ts = bool(segs) and all(hasattr(s, "start") or (isinstance(s, dict) and "start" in s) for s in segs[:3])
    rec = {"variant": variant, "model": MODELS[family], "load_s": round(load_s, 1), "wall_s": round(wall, 1),
           "peak_mem_GB": round(mx.get_peak_memory() / 1e9, 2), "words": len(text.split()),
           "timestamps": has_ts, "n_segments": len(segs), "text": text,
           "context_chars": len(kwargs.get("system_prompt", ""))}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    Path(out_dir, f"{variant}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in rec.items() if k != "text"}))


if __name__ == "__main__":
    main()
