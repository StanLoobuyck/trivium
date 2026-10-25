"""Browser-friendly copy of a lecture video for the in-app player.

Lecture recordings are often *fragmented* MP4 (one header + many fragments, as recorders write them). A
browser then only knows the duration of the fragments it has loaded, so long lectures seemed to stop
after a few minutes. Re-packing with `-c copy -movflags +faststart` (no re-encoding: ~2.5 s for 2 h,
same size) gives a normal MP4 with its index up front: full duration, instant seeking. The original
file is never touched.

No edit list (`-use_editlist 0`, PLAYER_VERSION 2, 2026-10-20): ffmpeg wrote a 0.08 s "empty edit" for the
video track (B-frame delay) that Zen/Firefox mis-read as ~3.9 s of no video: the sound started, the picture
froze for seconds and then lagged (mpv was fine, hence "the files are good"). Checked in headless Zen:
buffered from 3.92 s with the edit list, from 0.08 s without. Copies of an older version are re-made.

Sparse keyframes: some recordings have a keyframe only every 10 s; every seek then decodes up to 10 s of
video (measured: 250–400 ms per jump in Zen vs 12–100 ms with 2 s keyframes), so holding the arrow key
made the picture fall behind. Those are re-encoded with keyframes every 2 s on the laptop's *AMD* chip
(VA-API, ~27× real time, visually lossless: SSIM 0.997 at qp 24); never on the NVIDIA card (stays
asleep). Only the worker does that (minutes); opening a lecture always gets the fast repack first.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

BROWSER_VIDEO = {"h264"}          # plays everywhere in an MP4 (HEVC doesn't in Firefox)
BROWSER_AUDIO = {"aac", "mp3", "opus"}
PLAYER_VERSION = 2
SPARSE_KEYFRAMES_S = 4.0   # re-encode when keyframes are further apart than this
KEYFRAME_EVERY = 50        # frames (2 s at 25 fps)
_making = threading.Lock()  # the player fires several range requests at once: make the copy only once


def player_path(job_root: Path) -> Path:
    return job_root / "media" / "player.mp4"


def _version_path(job_root: Path) -> Path:
    return job_root / "media" / "player.json"


def _info(job_root: Path) -> dict:
    try:
        return json.loads(_version_path(job_root).read_text())
    except (OSError, ValueError):
        return {}  # copies from before versioning: version 1 (with the edit list)


def _current(job_root: Path, media: Path, reencode: bool = False) -> bool:
    out = player_path(job_root)
    if not out.exists() or out.stat().st_mtime < media.stat().st_mtime:
        return False
    info = _info(job_root)
    if info.get("version", 1) < PLAYER_VERSION:
        return False
    if reencode and "sparse" not in info:  # made before keyframes were measured: measure (and maybe re-encode)
        return False
    return not (reencode and info.get("sparse") and not info.get("reencoded"))


def keyframe_interval(media: Path, seconds: float = 120.0) -> float | None:
    """Average seconds between video keyframes over the first `seconds` (None if it can't be measured)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                          "-show_entries", "frame=pts_time", "-of", "csv=p=0", "-read_intervals", f"%+{seconds}",
                          str(media)], capture_output=True, text=True, check=False)
    times = [float(x) for x in out.stdout.split() if x.replace(".", "", 1).isdigit()]
    return (times[-1] - times[0]) / (len(times) - 1) if len(times) > 1 else None


def amd_render_node() -> Path | None:
    """A VA-API render node that is *not* the NVIDIA card (that one would wake up and drain the battery)."""
    for node in sorted(Path("/dev/dri").glob("renderD*")):
        try:
            driver = (Path("/sys/class/drm") / node.name / "device" / "driver").resolve().name
        except OSError:
            continue
        if driver in ("amdgpu", "i915", "xe", "radeon"):
            return node
    return None


def _codecs(media: Path) -> tuple[str | None, str | None]:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(media)],
                         capture_output=True, text=True, check=False)
    if out.returncode != 0:
        return None, None
    streams = json.loads(out.stdout).get("streams", [])
    video = next((s["codec_name"] for s in streams if s.get("codec_type") == "video"
                  and not s.get("disposition", {}).get("attached_pic")), None)
    audio = next((s["codec_name"] for s in streams if s.get("codec_type") == "audio"), None)
    return video, audio


def ensure_player(job_root: Path, media: Path, reencode: bool = False) -> Path | None:
    """The player copy (made if needed), or None when the original should be served as is
    (audio-only input, or a video codec that can't simply be re-packed). reencode=True (the worker):
    also re-encode recordings with sparse keyframes; False (opening a lecture): never wait minutes."""
    out = player_path(job_root)
    if _current(job_root, media, reencode):
        return out
    with _making:
        if _current(job_root, media, reencode):  # made by another request meanwhile
            return out
        return _make(job_root, media, out, reencode)


def _command(media: Path, part: Path, audio: str | None, node: Path | None) -> list[str]:
    """ffmpeg: re-pack (node None) or re-encode the video on that VA-API node; audio copied when the browser
    plays it, else a small AAC re-encode (e.g. PCM)."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    if node:
        cmd += ["-vaapi_device", str(node)]
    cmd += ["-i", str(media), "-map", "0:v:0"] + (["-map", "0:a:0"] if audio else [])
    if node:
        cmd += ["-vf", "format=nv12,hwupload", "-c:v", "h264_vaapi", "-g", str(KEYFRAME_EVERY), "-qp", "24"]
    else:
        cmd += ["-c:v", "copy"]
    if audio in BROWSER_AUDIO:
        cmd += ["-c:a", "copy"]
    elif audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    return cmd + ["-movflags", "+faststart", "-use_editlist", "0", "-f", "mp4", str(part)]


def _make(job_root: Path, media: Path, out: Path, reencode: bool = False) -> Path | None:
    video, audio = _codecs(media)
    if video not in BROWSER_VIDEO:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    gap = keyframe_interval(media)
    info = {"version": PLAYER_VERSION, "keyframe_s": round(gap, 1) if gap else None,
            "sparse": bool(gap and gap > SPARSE_KEYFRAMES_S), "reencoded": False}
    node = amd_render_node() if reencode and info["sparse"] else None
    ok = False
    if node:
        ok = subprocess.run(_command(media, part, audio, node), capture_output=True, check=False).returncode == 0
        info["reencoded"] = ok
    if not ok:  # normal case, or VA-API failed: the fast re-pack
        ok = subprocess.run(_command(media, part, audio, None), capture_output=True, check=False).returncode == 0
    if not ok:
        part.unlink(missing_ok=True)
        return None
    part.replace(out)
    _version_path(job_root).write_text(json.dumps(info))
    return out
