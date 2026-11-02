"""Slides and webcam side by side (pair.py) and how the inbox waits for it."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import pytest

from lecture import inbox, pair
from lecture import queue as q
from lecture.config import load_courses
from tests.test_inbox import box, put  # noqa: F401  (fixture)


def clip(path: Path, size: str, audio: bool) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25:d=2"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac"]
    subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", str(path)], check=True)
    return path


def streams(path: Path) -> list[dict]:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["streams"]



def test_parts_are_not_lectures_and_the_pair_waits_until_both_are_complete(box, monkeypatch):
    conf, root, queue, tick = box
    monkeypatch.setattr(q, "Queue", lambda: queue)
    dep = root / "digitale-elektronica"
    put(dep / "DEP les 11.webcam.mp4", 120)
    put(dep / "DEP les 11.mp4", 5)                       # the slides are still downloading
    put(dep / "DEP les 10.slides.mp4", 3600)              # original kept after an earlier combine
    (f,) = inbox.scan(conf, load_courses())
    assert Path(f["media"]).name == "DEP les 11.mp4"
    assert not f["ready"] and f["combine"] is None and "downloaded" in f["why"]

    (f,) = inbox.scan(conf, load_courses(), now=time.time() + inbox.STABLE_S)
    assert not f["ready"] and f["combine"].endswith("DEP les 11.webcam.mp4") and "combining" in f["why"]


def test_a_pair_that_cannot_be_combined_goes_on_as_slides(box, monkeypatch):
    conf, root, queue, tick = box
    monkeypatch.setattr(q, "Queue", lambda: queue)
    dep = root / "digitale-elektronica"
    put(dep / "les 3.webcam.mp4", 3600)
    slides = put(dep / "les 3.mp4", 3600)
    put(dep / "les 3.pdf", 3600)
    (dep / f".{slides.name}.combine-failed").touch()
    (f,) = inbox.scan(conf, load_courses())
    assert f["ready"] and "combine" not in f


@pytest.mark.parametrize("sound_on", ["slides", "webcam"])
def test_combine_puts_both_pictures_side_by_side(tmp_path, monkeypatch, sound_on):
    monkeypatch.setattr(pair, "amd_render_node", lambda: None)   # the CPU path, the same on every machine
    slides = clip(tmp_path / "les 4.mp4", "1280x720", audio=sound_on == "slides")
    webcam = clip(tmp_path / "les 4.webcam.mp4", "640x480", audio=sound_on == "webcam")
    assert pair.combine(slides, webcam)

    out = streams(tmp_path / "les 4.mp4")
    video = next(s for s in out if s["codec_type"] == "video")
    # Slides 1920×1080 + webcam 640 wide (480 tall after scaling, centred on black): one picture, no overlap.
    assert (video["width"], video["height"]) == (1920 + pair.WEBCAM_WIDTH, pair.HEIGHT)
    assert [s["codec_name"] for s in out if s["codec_type"] == "audio"] == ["aac"]
    assert (tmp_path / "les 4.slides.mp4").is_file() and webcam.is_file()
    assert not list(tmp_path.glob(".*"))                          # no leftovers


def test_combine_failure_is_marked_and_keeps_the_originals(tmp_path, monkeypatch):
    monkeypatch.setattr(pair, "amd_render_node", lambda: None)
    slides = put(tmp_path / "les 5.mp4", 0, b"not a video")
    webcam = put(tmp_path / "les 5.webcam.mp4", 0, b"not a video")
    assert not pair.combine(slides, webcam)
    assert pair.failed(slides) and slides.read_bytes() == b"not a video" and webcam.is_file()
