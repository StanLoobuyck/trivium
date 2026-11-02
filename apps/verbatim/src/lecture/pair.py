"""Recordings with two pictures (Velox, 2026-11-02): slides and webcam side by side in one video.

Some Kaltura recordings have the slides and the webcam as two separate streams. With "downloads to Verbatim" on,
Velox saves the webcam first as "<title>.webcam.mp4", then the slides as "<title>.mp4". Once both have stopped
changing, the inbox has them combined here: the slides at full height on the left, the webcam smaller on the
right, centred, never overlapping. The combined video takes the slides' name, so it is processed as usual and
Sequo still matches it on that file name; the originals stay next to it as "<title>.slides.mp4" and
"<title>.webcam.mp4", which the inbox skips.

Encoding: on the laptop's AMD chip when there is one (VA-API, as player.py), else libx264. Runs in a thread per
pair, so the worker isn't blocked for the minutes it takes. A pair that can't be combined is marked, and the
inbox then takes the slides alone.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from .naming import VIDEO_EXT
from .player import BROWSER_AUDIO, KEYFRAME_EVERY, _codecs, amd_render_node

WEBCAM = ".webcam"
SLIDES = ".slides"
HEIGHT = 1080       # px: the slides at full HD height
WEBCAM_WIDTH = 640  # px: about a third of 16:9 slides, still a readable face
_running: dict[str, threading.Thread] = {}
_lock = threading.Lock()


def is_part(video: Path) -> bool:
    """One half of a pair (or an original kept after combining): not a lecture of its own."""
    return video.stem.lower().endswith((WEBCAM, SLIDES))


def webcam_of(video: Path) -> Path | None:
    """The webcam picture that goes with this recording, if Velox saved one."""
    for ext in sorted(VIDEO_EXT):
        candidate = video.with_name(f"{video.stem}{WEBCAM}{ext}")
        if candidate.is_file():
            return candidate
    return None


def _failed_marker(video: Path) -> Path:
    return video.with_name(f".{video.name}.combine-failed")


def failed(video: Path) -> bool:
    return _failed_marker(video).exists()


def busy(video: Path) -> bool:
    with _lock:
        thread = _running.get(str(video))
        return bool(thread and thread.is_alive())


def command(slides: Path, webcam: Path, out: Path, audio_from: int | None, audio_codec: str | None,
            node: Path | None) -> list[str]:
    """ffmpeg: both pictures next to each other on black, the sound of one of them."""
    layout = (f"[0:v]scale=-2:{HEIGHT},setsar=1[s];"
              f"[1:v]scale={WEBCAM_WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,setsar=1,"
              f"pad={WEBCAM_WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black[c];"
              f"[s][c]hstack=inputs=2,format=nv12" + (",hwupload" if node else "") + "[v]")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if node:
        cmd += ["-vaapi_device", str(node)]
    cmd += ["-i", str(slides), "-i", str(webcam), "-filter_complex", layout, "-map", "[v]"]
    if audio_from is not None:
        cmd += ["-map", f"{audio_from}:a:0"]
        cmd += ["-c:a", "copy"] if audio_codec in BROWSER_AUDIO else ["-c:a", "aac", "-b:a", "128k"]
    if node:
        cmd += ["-c:v", "h264_vaapi", "-qp", "24"]
    else:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26"]
    return cmd + ["-g", str(KEYFRAME_EVERY), "-movflags", "+faststart", "-use_editlist", "0", "-f", "mp4", str(out)]


def combine(video: Path, webcam: Path) -> bool:
    """Combine now (minutes). On success `video` is the combined picture and the originals are kept beside it."""
    part = video.with_name(f".{video.stem}.combining.mp4")
    _, slides_audio = _codecs(video)
    _, webcam_audio = _codecs(webcam)
    audio_from, audio_codec = (0, slides_audio) if slides_audio else ((1, webcam_audio) if webcam_audio else (None, None))
    ok = False
    for node in ([amd_render_node()] if amd_render_node() else []) + [None]:  # AMD chip first, else the CPU
        cmd = command(video, webcam, part, audio_from, audio_codec, node)
        if subprocess.run(cmd, capture_output=True, check=False).returncode == 0 and part.stat().st_size > 0:
            ok = True
            break
    if not ok:
        part.unlink(missing_ok=True)
        _failed_marker(video).touch()
        return False
    video.replace(video.with_name(f"{video.stem}{SLIDES}{video.suffix}"))
    part.replace(video.with_suffix(".mp4"))
    return True


def start(video: Path, webcam: Path, rep=None) -> None:
    """Combine in the background, once per pair."""
    with _lock:
        key = str(video)
        if key in _running and _running[key].is_alive():
            return

        def run():
            ok = combine(video, webcam)
            if rep:
                rep(f"inbox: {'combined' if ok else 'could not combine'} slides and webcam of {video.name}")

        _running[key] = threading.Thread(target=run, name=f"combine {video.name}", daemon=True)
        _running[key].start()
