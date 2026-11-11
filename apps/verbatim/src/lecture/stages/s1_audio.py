"""Stage 1: probe the input, extract 16 kHz mono FLAC, detect silences on the unfiltered audio."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

from ..config import Config, SilenceConfig
from ..job import Job
from ..report import Reporter
from ..util import hash_data, write_json

SAMPLE_RATE = 16000


class NoAudioError(RuntimeError):
    pass


def probe(media: Path) -> dict:
    """Duration (s) and stream info of a media file."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(media)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe can't read {media}: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    streams = data.get("streams", [])
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    video = [s for s in streams if s.get("codec_type") == "video"
             and not s.get("disposition", {}).get("attached_pic")]
    if not audio:
        raise NoAudioError(f"{media} has no audio stream")
    duration = float(data.get("format", {}).get("duration") or audio[0].get("duration") or 0.0)
    return {"duration_s": duration, "audio_streams": len(audio), "has_video": bool(video),
            "audio_codec": audio[0].get("codec_name")}


def _run_ffmpeg_with_progress(cmd: list[str], duration_s: float, reporter: Reporter, text: str) -> None:
    proc = subprocess.Popen(cmd + ["-progress", "pipe:1", "-nostats"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for line in proc.stdout:
        key, _, value = line.strip().partition("=")
        if key == "out_time_us" and value.isdigit() and duration_s > 0:
            reporter.progress(min(int(value) / 1e6, duration_s), duration_s, text)
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.strip()[-2000:]}")


def extract_audio(media: Path, out: Path, filters: str, duration_s: float, reporter: Reporter) -> None:
    part = out.with_name(out.name + ".part")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(media),
           "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE)]
    # 16-bit: AAC decodes to float and ffmpeg's FLAC encoder would otherwise pick 24-bit (2× the size,
    # no benefit for Whisper). Not part of the stage hash: same content, so existing jobs stay valid.
    chain = ",".join(f for f in (filters, "aformat=sample_fmts=s16") if f)
    cmd += ["-af", chain, "-c:a", "flac", "-f", "flac", str(part)]
    _run_ffmpeg_with_progress(cmd, duration_s, reporter, "Extracting audio")
    part.replace(out)


def frame_levels_db(media: Path, frame_s: float) -> np.ndarray:
    """RMS level per frame in dBFS of the unfiltered mono 16 kHz audio, streamed (never all in memory)."""
    frame = int(round(frame_s * SAMPLE_RATE))
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(media),
           "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    levels: list[np.ndarray] = []
    leftover = np.zeros(0, dtype=np.int16)
    block = frame * 2 * 2000  # bytes: 2000 frames per read
    while data := proc.stdout.read(block):
        samples = np.concatenate([leftover, np.frombuffer(data[: len(data) // 2 * 2], dtype=np.int16)])
        n = len(samples) // frame
        frames = samples[: n * frame].reshape(n, frame).astype(np.float64) / 32768.0
        levels.append(20 * np.log10(np.sqrt(np.mean(frames**2, axis=1)) + 1e-10))
        leftover = samples[n * frame:]
    stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed while measuring levels: {stderr.strip()[-2000:]}")
    return np.concatenate(levels) if levels else np.zeros(0)


def detect_silences(levels_db: np.ndarray, cfg: SilenceConfig) -> dict:
    """Silent intervals (s) below a threshold relative to the noise floor (dBFS)."""
    if len(levels_db) == 0:
        return {"floor_db": None, "threshold_db": cfg.max_threshold_db, "silences": []}
    floor = float(np.percentile(levels_db, cfg.floor_percentile))
    threshold = float(np.clip(floor + cfg.margin_db, cfg.min_threshold_db, cfg.max_threshold_db))
    # Guard for recordings with little silence or low speech level: most frames are speech, so the
    # threshold must stay well below the median level.
    threshold = min(threshold, float(np.median(levels_db)) - 10.0)
    quiet = np.concatenate([[False], levels_db < threshold, [False]])
    edges = np.flatnonzero(np.diff(quiet.astype(np.int8)))
    min_frames = cfg.min_silence_s / cfg.frame_s
    silences = [
        [round(a * cfg.frame_s, 3), round(b * cfg.frame_s, 3)]
        for a, b in zip(edges[::2], edges[1::2])
        if b - a >= min_frames
    ]
    return {"floor_db": round(floor, 1), "threshold_db": round(threshold, 1), "silences": silences}


def input_hash(job: Job, conf: Config) -> str:
    return hash_data({"media": job.manifest["input"]["fingerprint"], "filters": conf.audio.filters,
                      "silence": conf.audio.silence.model_dump()})


def run(job: Job, conf: Config, reporter: Reporter) -> None:
    info = probe(job.media)
    if info["audio_streams"] > 1:
        reporter.warn(f"input has {info['audio_streams']} audio streams; using the first one")
    job.audio_dir.mkdir(parents=True, exist_ok=True)
    extract_audio(job.media, job.full_audio, conf.audio.filters, info["duration_s"], reporter)
    duration = probe(job.full_audio)["duration_s"]

    reporter.info("Measuring levels for silence detection")
    levels = frame_levels_db(job.media, conf.audio.silence.frame_s)
    silences = detect_silences(levels, conf.audio.silence)
    write_json(job.silences_path, {"duration_s": duration, "frame_s": conf.audio.silence.frame_s, **silences})
    total_silence = sum(b - a for a, b in silences["silences"])
    reporter.info(f"Audio: {duration / 60:.1f} min; noise floor {silences['floor_db']} dBFS, "
                  f"silence threshold {silences['threshold_db']} dBFS, "
                  f"{len(silences['silences'])} silences ({total_silence / 60:.1f} min)")
    job.mark_stage("audio", "done", input_hash(job, conf), duration_s=duration, has_video=info["has_video"],
                   floor_db=silences["floor_db"], threshold_db=silences["threshold_db"])
