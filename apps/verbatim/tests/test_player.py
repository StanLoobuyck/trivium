"""Player copy: fragmented MP4 recordings (long lectures stopped early in the browser) → normal MP4."""

import struct
import subprocess
import sys

import pytest

from lecture.player import ensure_player, player_path


def _boxes(path):
    data, out, pos = path.read_bytes(), [], 0
    while pos < len(data):
        size, typ = struct.unpack(">I4s", data[pos:pos + 8])
        out.append(typ.decode())
        pos += size
    return out


def test_fragmented_recording_is_repacked_with_index_first(tmp_path):
    src = tmp_path / "lecture.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "12", "-c:v", "libx264", "-g", "20",
                    "-c:a", "aac", "-movflags", "frag_keyframe+empty_moov", str(src)], check=True)
    assert "moof" in _boxes(src)  # like the real lecture recordings
    out = ensure_player(tmp_path / "job", src)
    assert out == player_path(tmp_path / "job")
    boxes = _boxes(out)
    assert "moof" not in boxes and boxes.index("moov") < boxes.index("mdat")
    duration = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                               str(out)], capture_output=True, text=True).stdout
    assert abs(float(duration) - 12) < 0.5
    mtime = out.stat().st_mtime
    assert ensure_player(tmp_path / "job", src) == out and out.stat().st_mtime == mtime  # made once


def test_audio_only_is_served_as_is(tmp_path):
    src = tmp_path / "lecture.m4a"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440",
                    "-t", "3", "-c:a", "aac", str(src)], check=True)
    assert ensure_player(tmp_path / "job", src) is None


def test_no_edit_list_and_old_copies_are_remade(tmp_path):
    # B-frames → ffmpeg would write a short "empty edit" for the video track, which Zen/Firefox mis-read as
    # seconds without video (sound plays, picture frozen, then lagging). The copy must have no elst.
    src = tmp_path / "lecture.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-bf", "3", "-g", "50",
                    "-c:a", "aac", "-movflags", "frag_keyframe+empty_moov", str(src)], check=True)
    job = tmp_path / "job"
    out = ensure_player(job, src)
    assert b"elst" not in out.read_bytes()[:200_000]
    # a copy from before versioning (no player.json) is made again
    (job / "media" / "player.json").unlink()
    out.write_bytes(b"old copy")
    assert ensure_player(job, src).read_bytes() != b"old copy"


@pytest.mark.skipif(sys.platform == "win32", reason="VA-API (/dev/dri) is Linux-only")
def test_sparse_keyframes_are_measured_and_only_the_worker_reencodes(tmp_path, monkeypatch):
    from pathlib import Path

    from lecture import player

    src = tmp_path / "sparse.mp4"  # a keyframe every 10 s, like RZL les 1
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "25", "-c:v", "libx264", "-g", "250",
                    "-keyint_min", "250", "-sc_threshold", "0", "-c:a", "aac", str(src)], check=True)
    assert 9 < player.keyframe_interval(src) < 11
    calls = []
    real_run = subprocess.run
    monkeypatch.setattr(player.subprocess, "run", lambda cmd, **kw: (calls.append(cmd), real_run(cmd, **kw))[1])
    monkeypatch.setattr(player, "amd_render_node", lambda: Path("/dev/dri/renderD128"))
    # opening the lecture: fast re-pack only, never the minutes-long re-encode
    player.ensure_player(tmp_path / "job", src)
    assert not any("h264_vaapi" in c for c in calls)
    info = player._info(tmp_path / "job")
    assert info["sparse"] and not info["reencoded"]
    # the worker: tries the AMD encoder; when that fails (no VA-API here) it keeps the re-pack
    calls.clear()
    assert player.ensure_player(tmp_path / "job", src, reencode=True) is not None
    vaapi = [c for c in calls if "h264_vaapi" in c]
    assert vaapi and "-g" in vaapi[0] and vaapi[0][vaapi[0].index("-g") + 1] == "50"
    assert vaapi[0][vaapi[0].index("-vaapi_device") + 1] == "/dev/dri/renderD128"


def test_render_node_is_never_the_nvidia_card(tmp_path, monkeypatch):
    from pathlib import Path

    from lecture import player

    dri, drm = tmp_path / "dri", tmp_path / "drm"
    dri.mkdir()
    for node, driver in (("renderD128", "nvidia"), ("renderD129", "amdgpu")):
        (dri / node).touch()
        (drm / node / "device").mkdir(parents=True)
        (tmp_path / "drivers" / driver).mkdir(parents=True)
        (drm / node / "device" / "driver").symlink_to(tmp_path / "drivers" / driver)
    real_path = Path
    monkeypatch.setattr(player, "Path", lambda p: real_path(str(p).replace("/dev/dri", str(dri)).replace("/sys/class/drm", str(drm))))
    assert player.amd_render_node().name == "renderD129"
