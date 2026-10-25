"""Live smoke test against the real Groq API (uses free quota).

Run with:  LECTURE_LIVE_CLIP=/path/to/60s-clip.mp4 uv run pytest -m live
"""

import os
from pathlib import Path

import pytest

from lecture import pipeline
from lecture.config import load_config, load_keys
from lecture.job import Job
from lecture.report import NullReporter
from lecture.util import read_json

CLIP = os.environ.get("LECTURE_LIVE_CLIP")


@pytest.mark.live
@pytest.mark.skipif(not CLIP or not load_keys()["GROQ_API_KEY"], reason="needs LECTURE_LIVE_CLIP and GROQ_API_KEY")
def test_live_transcription(tmp_path):
    conf = load_config().model_copy(deep=True)
    conf.paths.jobs_dir = tmp_path / "jobs"
    job = Job.create(conf.paths.jobs_dir, Path(CLIP), "live", os.environ.get("LECTURE_LIVE_LANG", "nl"),
                     "live", "2026-01-01")
    pipeline.run_job(job, conf, NullReporter())
    data = read_json(job.root / "transcript_raw.json")
    assert data["segments"], "no speech recognised"
    assert all("words" in s for s in data["segments"])
    assert (job.outputs / "subtitles.srt").stat().st_size > 0
