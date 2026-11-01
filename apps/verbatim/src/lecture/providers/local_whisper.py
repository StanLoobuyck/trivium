"""Local Whisper (faster-whisper / CTranslate2) on an NVIDIA GPU.

Returns responses in the same shape as Groq's verbose_json, so stitching, the repair pass, eval and
subtitles work unchanged. Needs the optional `local` extra: `uv sync --extra local`.
"""

from __future__ import annotations

import ctypes
import gc
import subprocess
import time
from pathlib import Path

import numpy as np

from ..config import Config
from ..report import NullReporter, Reporter
from .base import Transcription

SAMPLE_RATE = 16000
_preloaded = False


class LocalUnavailable(RuntimeError):
    """Local Whisper can't run here (no extra installed, no CUDA, model won't load)."""


def preload_cuda_libraries() -> list[str]:
    """Load cuBLAS/cuDNN from the pip wheels (nvidia-*-cu12) so CTranslate2 finds them.

    CTranslate2 dlopen()s 'libcublas.so.12' etc. by name; libraries already loaded with RTLD_GLOBAL
    satisfy that, so no system CUDA install or LD_LIBRARY_PATH is needed.
    """
    global _preloaded
    if _preloaded:
        return []
    loaded = []
    try:
        import nvidia.cublas
        import nvidia.cudnn
    except ImportError:
        return loaded  # fall back to system libraries, if any
    # order matters: cuBLASLt before cuBLAS, the cuDNN core before its sub-libraries
    patterns = [(nvidia.cublas, ["libcublasLt.so.*", "libcublas.so.*"]),
                (nvidia.cudnn, ["libcudnn.so.*", "libcudnn_graph.so.*", "libcudnn_*.so.*"])]
    for pkg, globs in patterns:
        lib_dir = Path(next(iter(pkg.__path__))) / "lib"
        seen = set()
        for g in globs:
            for so in sorted(lib_dir.glob(g)):
                if so.name in seen:
                    continue
                seen.add(so.name)
                ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
                loaded.append(so.name)
    _preloaded = True
    return loaded


def load_audio(path: Path) -> np.ndarray:
    """16 kHz mono float32 via ffmpeg (avoids faster-whisper's PyAV decoder, which breaks on newer PyAV)."""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1",
         "-ar", str(SAMPLE_RATE), "pipe:1"],
        capture_output=True, check=True,
    )
    return np.frombuffer(out.stdout, dtype=np.float32)


class LocalWhisper:
    name = "local"

    def __init__(self, conf: Config, reporter: Reporter | None = None):
        self.conf = conf
        self.lc = conf.stt.local
        self.reporter = reporter or NullReporter()
        self._model = None
        self._compute_type: str | None = None

    @property
    def model_label(self) -> str:
        return f"local:{self.lc.model}"

    def _load(self, compute_types: list[str] | None = None):
        if self._model is not None:
            return self._model
        try:
            preload_cuda_libraries()
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise LocalUnavailable("faster-whisper not installed (run: uv sync --extra local)") from exc
        except OSError as exc:
            raise LocalUnavailable(f"CUDA libraries could not be loaded: {exc}") from exc
        last_error: Exception | None = None
        for compute_type in compute_types or self.lc.compute_types:
            try:
                t0 = time.time()
                self._model = WhisperModel(self.lc.model, device=self.lc.device, compute_type=compute_type)
                self._compute_type = compute_type
                self.reporter.info(f"Local Whisper {self.lc.model} loaded on {self.lc.device} "
                                   f"({compute_type}) in {time.time() - t0:.0f} s")
                return self._model
            except (RuntimeError, ValueError) as exc:  # e.g. out of memory, unsupported compute type
                last_error = exc
                self.reporter.warn(f"Local Whisper with {compute_type} failed: {exc}")
        raise LocalUnavailable(f"model {self.lc.model} could not be loaded: {last_error}")

    def check(self) -> None:
        """Raise LocalUnavailable if local transcription can't work (used to pick the provider)."""
        self._load()

    def close(self) -> None:
        """Free the GPU memory (the long-running worker keeps the process alive between jobs)."""
        if self._model is not None:
            self._model = None
            gc.collect()

    def transcribe(self, audio_path: Path, duration_s: float, language: str, prompt: str,
                   model: str | None = None) -> Transcription:
        audio = load_audio(audio_path)
        try:
            return self._transcribe(audio, language, prompt)
        except RuntimeError as exc:
            if "out of memory" not in str(exc).lower():
                raise
            # GPU memory taken mid-run (e.g. a game started): retry once with the smaller compute types.
            # Never switch to Groq here — that would mix providers within one run.
            smaller = self.lc.compute_types[self.lc.compute_types.index(self._compute_type) + 1:]
            self.reporter.warn(f"Local Whisper ran out of GPU memory ({self._compute_type})"
                               + (f"; retrying with {smaller[0]}" if smaller else ""))
            self.close()
            if not smaller:
                raise RuntimeError("GPU out of memory — free the GPU and run `lecture resume`") from exc
            try:
                self._load(smaller)
                return self._transcribe(audio, language, prompt)
            except (LocalUnavailable, RuntimeError) as exc2:
                self.close()
                raise RuntimeError(f"GPU out of memory ({exc2}) — free the GPU and run `lecture resume`") from exc2

    def _transcribe(self, audio: np.ndarray, language: str, prompt: str) -> Transcription:
        wm = self._load()
        lc = self.lc
        t0 = time.time()
        segments, info = wm.transcribe(
            audio,
            language=language,
            task="transcribe",
            beam_size=lc.beam_size,
            temperature=list(lc.temperatures),
            condition_on_previous_text=lc.condition_on_previous_text,
            initial_prompt=prompt or None,
            word_timestamps=True,
            vad_filter=lc.vad_filter,
            compression_ratio_threshold=self.conf.stitch.compression_ratio,
            log_prob_threshold=self.conf.stitch.no_speech_logprob,
            no_speech_threshold=self.conf.stitch.no_speech_prob,
        )
        segs, words = [], []
        for i, s in enumerate(segments):  # generator: decoding happens here
            segs.append({
                "id": i, "start": round(float(s.start), 3), "end": round(float(s.end), 3), "text": s.text,
                "avg_logprob": float(s.avg_logprob), "no_speech_prob": float(s.no_speech_prob),
                "compression_ratio": float(s.compression_ratio), "temperature": float(s.temperature),
            })
            words += [{"word": w.word.strip(), "start": round(float(w.start), 3), "end": round(float(w.end), 3)}
                      for w in (s.words or [])]
        elapsed = time.time() - t0
        response = {
            "task": "transcribe", "language": info.language, "duration": info.duration,
            "text": "".join(s["text"] for s in segs), "segments": segs, "words": words,
            "x_local": {"model": lc.model, "compute_type": self._compute_type, "beam_size": lc.beam_size,
                        "vad_filter": lc.vad_filter, "elapsed_s": round(elapsed, 2),
                        "realtime_factor": round(info.duration / elapsed, 1) if elapsed > 0 else None},
        }
        return Transcription(response=response, model=self.model_label, attempts=1)
