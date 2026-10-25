"""Phase 8.1 smoke test: transcribe one clip with mlx-whisper and report speed and memory.

uv run python smoke.py CLIP.flac --model mlx-community/whisper-large-v3-mlx --prompt "..." [--language nl]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time

import mlx.core as mx
import mlx_whisper


def duration_s(path: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True)
    return float(out.stdout)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--model", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--language", default="nl")
    ap.add_argument("--runs", type=int, default=2, help="first run includes model load")
    args = ap.parse_args()

    dur = duration_s(args.clip)
    for i in range(args.runs):
        mx.reset_peak_memory()
        t0 = time.perf_counter()
        result = mlx_whisper.transcribe(
            args.clip, path_or_hf_repo=args.model, language=args.language,
            initial_prompt=args.prompt or None, condition_on_previous_text=False,
            word_timestamps=True, temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        )
        wall = time.perf_counter() - t0
        print(json.dumps({"run": i + 1, "model": args.model, "audio_s": round(dur, 1), "wall_s": round(wall, 2),
                          "x_realtime": round(dur / wall, 1), "peak_mem_GB": round(mx.get_peak_memory() / 1e9, 2),
                          "segments": len(result["segments"])}))
    print("TEXT:", result["text"].strip())


if __name__ == "__main__":
    main()
