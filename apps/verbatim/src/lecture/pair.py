"""Recordings with two pictures (Velox, 2026-11-02): slides and webcam side by side in one video.

Some Kaltura recordings have the slides and the webcam as two separate streams. With "downloads to Verbatim" on,
Velox saves the webcam first as "<title>.webcam.mp4", then the slides as "<title>.mp4". Once both have stopped
changing, the inbox has them combined here: the slides at full height on the left, the webcam smaller on the
right, centred, never overlapping. The combined video takes the slides' name, so it is processed as usual and
Sequo still matches it on that file name; the originals stay next to it as "<title>.slides.mp4" and
"<title>.webcam.mp4", which the inbox skips.

Where (user's choice, 2026-11-02: the laptop stays cool): on the Mac at home when it answers (mac/server.py,
libx264 on its 8 fast cores, ~11x real time; sending both files and getting the result back took ~30 s for a
19 min lecture), else the laptop's AMD chip (VA-API, as player.py), and only as a last resort the laptop's CPU.
Runs in a thread per pair, so the worker isn't blocked for the minutes it takes. A pair that can't be combined is
marked, and the inbox then takes the slides alone.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import httpx

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


def _sibling(video: Path, tag: str) -> Path | None:
    for ext in sorted(VIDEO_EXT):
        candidate = video.with_name(f"{video.stem}{tag}{ext}")
        if candidate.is_file():
            return candidate
    return None


def webcam_of(video: Path) -> Path | None:
    """The webcam picture that goes with this recording, if Velox saved one and it wasn't combined yet: a combined
    recording keeps its slides beside it as "<title>.slides.<ext>", and must never be combined again."""
    if _sibling(video, SLIDES):
        return None
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


def stopped(video: Path) -> bool:
    """The user pressed Stop on this pair (the UI runs in another process: it writes the inbox's ignore list)."""
    from . import config as cfgmod
    from . import inbox

    try:
        return str(video.resolve()) in inbox.ignored(cfgmod.load_config())
    except Exception:  # noqa: BLE001 - no config: nothing was stopped
        return False


def _run_stoppable(cmd: list[str], video: Path) -> tuple[int, str]:
    """ffmpeg, ended within a second when the user stops the pair."""
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    while True:
        try:
            _, err = proc.communicate(timeout=1.0)
            return proc.returncode, err or ""
        except subprocess.TimeoutExpired:
            if stopped(video):
                proc.terminate()
                proc.communicate()
                return -1, "stopped by the user"


def on_mac(video: Path, webcam: Path, part: Path, audio: str) -> str | None:
    """Combine on the Mac's model server. None when done, else why not (not set up, not reachable, failed)."""
    from . import config as cfgmod

    try:
        mac = cfgmod.load_config().stt.mac
        token = cfgmod.load_keys()["LECTURE_MAC_TOKEN"]
    except Exception as exc:  # noqa: BLE001 - no Mac configured is a normal case
        return f"no Mac configured ({type(exc).__name__})"
    if not (mac and mac.url and token):
        return "no Mac configured"
    try:
        with httpx.Client(base_url=mac.url, headers={"Authorization": f"Bearer {token}"},
                          timeout=httpx.Timeout(3600.0, connect=mac.health_timeout_s)) as client:
            client.get("/health").raise_for_status()
            with video.open("rb") as s, webcam.open("rb") as w, client.stream(
                    "POST", "/v1/video/side-by-side",
                    files={"slides": (video.name, s, "video/mp4"), "webcam": (webcam.name, w, "video/mp4")},
                    data={"height": str(HEIGHT), "webcam_width": str(WEBCAM_WIDTH), "audio": audio}) as r:
                if r.status_code != 200:
                    return f"Mac answered {r.status_code}: {r.read()[:200].decode(errors='replace')}"
                with part.open("wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        if stopped(video):
                            break
                        f.write(chunk)
    except httpx.HTTPError as exc:
        part.unlink(missing_ok=True)
        return f"Mac not reachable ({type(exc).__name__})"
    return None if part.exists() and part.stat().st_size > 0 else "Mac sent an empty file"


def combine(video: Path, webcam: Path, rep=None, use_mac: bool = True) -> bool:
    """Combine now (minutes). On success `video` is the combined picture and the originals are kept beside it."""
    say = rep or (lambda _msg: None)
    if _sibling(video, SLIDES):  # combined before: the originals must stay as they are
        say(f"inbox: {video.name} was combined before; not again")
        return False
    part = video.with_name(f".{video.stem}.combining.mp4")
    _, slides_audio = _codecs(video)
    _, webcam_audio = _codecs(webcam)
    audio_from, audio_codec = (0, slides_audio) if slides_audio else ((1, webcam_audio) if webcam_audio else (None, None))
    why = on_mac(video, webcam, part, {0: "slides", 1: "webcam"}.get(audio_from, "none")) if use_mac else "off"
    ok = why is None
    if stopped(video):
        part.unlink(missing_ok=True)
        say(f"inbox: combining {video.name} stopped by the user")
        return False
    if not ok:
        say(f"inbox: combining {video.name} on the laptop (Mac: {why})")
    node = amd_render_node()
    for hw in ([node] if node else []) + [None]:  # the laptop's AMD chip, the CPU only as a last resort
        if ok:
            break
        code, err = _run_stoppable(command(video, webcam, part, audio_from, audio_codec, hw), video)
        if stopped(video):
            part.unlink(missing_ok=True)
            say(f"inbox: combining {video.name} stopped by the user")
            return False
        ok = code == 0 and part.exists() and part.stat().st_size > 0
        if not ok:
            say(f"inbox: combining on {'the AMD chip' if hw else 'the CPU'} failed: {err.strip()[-300:]}")
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
            ok = combine(video, webcam, rep)
            if rep:
                rep(f"inbox: {'combined' if ok else 'could not combine'} slides and webcam of {video.name}")

        _running[key] = threading.Thread(target=run, name=f"combine {video.name}", daemon=True)
        _running[key].start()
