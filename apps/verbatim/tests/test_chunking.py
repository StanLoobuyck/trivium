import numpy as np
import pytest

from lecture.config import SilenceConfig
from lecture.stages import s3_chunk
from lecture.stages.s1_audio import detect_silences, frame_levels_db

from .conftest import make_audio


def cfg(conf, **kw):
    return conf.chunking.model_copy(update=kw)


def test_long_silence_splits_regions_and_is_skipped(conf):
    c = cfg(conf, skip_silence_over_s=15, skip_padding_s=0.5)
    regions, skipped = s3_chunk.speech_regions(300, [(100, 160), (200, 201)], c)
    assert regions == [(0, 100.5), (159.5, 300)]
    assert skipped == [(100.5, 159.5)]


def test_leading_silence_and_tiny_island_dropped(conf):
    c = cfg(conf, skip_silence_over_s=15, skip_padding_s=0.5, min_region_s=1.0)
    # 0–30 s silence (before class), 30.0–30.6 a click, 30.6–60 silence, speech until 200
    regions, skipped = s3_chunk.speech_regions(200, [(0, 30.0), (30.6, 60)], c)
    assert regions == [(59.5, 200)]
    assert skipped == [(0.0, 59.5)]


def test_cut_at_longest_silence_near_target(conf):
    c = cfg(conf, target_s=600, search_window_s=30)
    silences = [(590, 590.5), (612, 614), (640, 650)]  # 640–650 is outside ±30 s of 600
    pieces = s3_chunk.split_region(0, 1300, silences, c)
    assert pieces[0] == (0, 613, 0, 613, False)
    assert pieces[1][0] == 613 and not pieces[1][4]


def test_hard_cut_with_overlap_when_no_silence(conf):
    c = cfg(conf, target_s=600, hard_cut_overlap_s=2.0)
    pieces = s3_chunk.split_region(0, 1300, [], c)
    assert pieces[0] == (0, 601, 0, 600, True)
    assert pieces[1] == (599, 1300, 600, 1300, True)


def test_no_chunk_shorter_than_half_target_at_end(conf):
    c = cfg(conf, target_s=600)
    pieces = s3_chunk.split_region(0, 850, [], c)  # 850 < 1.5 × 600 → one chunk
    assert len(pieces) == 1


def test_short_target_window_scales(conf):
    c = cfg(conf, target_s=150, search_window_s=30)
    # window = min(30, 0.2×150) = 30 → a silence at 175 (25 s away) is accepted
    pieces = s3_chunk.split_region(0, 400, [(174.5, 175.5)], c)
    assert pieces[0][1] == 175


def test_plan_and_select_range(conf):
    c = cfg(conf, target_s=600)
    plan = s3_chunk.plan_chunks(3000, [(1200, 1201), (2400, 2401)], c)
    chunks = s3_chunk.chunks_from_plan(plan)
    assert [round(ch.keep_start) for ch in chunks] == [0, 600, 1200, 1800, 2400] or len(chunks) >= 4
    covered = sum(ch.keep_end - ch.keep_start for ch in chunks)
    assert covered == pytest.approx(3000)
    sel = s3_chunk.select_range(chunks, 1250, 1300)
    assert len(sel) == 1 and sel[0].keep_start <= 1250 < sel[0].keep_end


def test_detect_silences_relative_threshold():
    sc = SilenceConfig(frame_s=0.05, min_silence_s=0.4, floor_percentile=10, margin_db=8,
                       min_threshold_db=-50, max_threshold_db=-30)
    levels = np.full(200, -20.0)       # speech at −20 dBFS
    levels[50:70] = -45.0              # 1.0 s silence
    levels[100:105] = -45.0            # 0.25 s: too short
    levels[:30] = -45.0                # make the floor low enough
    out = detect_silences(levels, sc)
    assert out["threshold_db"] == pytest.approx(-37.0)
    assert [0.0, 1.5] in out["silences"] and [2.5, 3.5] in out["silences"]
    assert all(b - a >= 0.4 for a, b in out["silences"])


def test_frame_levels_from_real_audio(tmp_path):
    path = make_audio(tmp_path / "a.flac", [("tone", 2), ("quiet", 1), ("tone", 1)])
    levels = frame_levels_db(path, 0.05)
    assert len(levels) == pytest.approx(80, abs=2)
    assert levels[10] > -25 and levels[50] < -50   # tone ≈ −21 dBFS (ffmpeg sine amplitude 1/8), quiet ≈ −60 dBFS


def test_threshold_stays_below_quiet_speech():
    sc = SilenceConfig(frame_s=0.05, min_silence_s=0.4, floor_percentile=10, margin_db=8,
                       min_threshold_db=-50, max_threshold_db=-30)
    levels = np.full(200, -36.0)       # quiet recording: speech at −36 dBFS, hardly any pauses
    levels[50:60] = -60.0
    out = detect_silences(levels, sc)
    assert out["threshold_db"] <= -46.0
    assert out["silences"] == [[2.5, 3.0]]
