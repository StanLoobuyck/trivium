"""Job folder: manifest.json, stage status, STT runs, log file."""

from __future__ import annotations

import logging
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from . import oscompat
from .util import file_fingerprint, read_json, slugify, write_json

MANIFEST_VERSION = 1


class JobLockedError(RuntimeError):
    pass


class Job:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manifest_path = self.root / "manifest.json"
        self.manifest: dict[str, Any] = read_json(self.manifest_path)

    # --- creation / lookup ---------------------------------------------------------------

    @classmethod
    def create(cls, jobs_dir: Path, media: Path, course_id: str, language: str,
               title: str, date: str) -> Job:
        media = media.resolve()
        base = f"{date}_{course_id}_{slugify(title)}"
        root = jobs_dir / base
        n = 2
        while root.exists():
            root = jobs_dir / f"{base}-{n}"
            n += 1
        root.mkdir(parents=True)
        manifest = {
            "version": MANIFEST_VERSION,
            "created": datetime.now().isoformat(timespec="seconds"),
            "course": course_id,
            "language": language,
            "title": title,
            "date": date,
            "input": {"media": str(media), "size": media.stat().st_size,
                      "fingerprint": file_fingerprint(media)},
            "stages": {},
            "stt": {"current_run": None, "runs": {}},
        }
        write_json(root / "manifest.json", manifest)
        return cls(root)

    @classmethod
    def find(cls, jobs_dir: Path, media: Path, course_id: str) -> Job | None:
        """An existing job for the same input file (by fingerprint) and course, newest first."""
        if not jobs_dir.exists():
            return None
        fingerprint = file_fingerprint(media)
        for manifest in sorted(jobs_dir.glob("*/manifest.json"), reverse=True):
            try:
                data = read_json(manifest)
            except (OSError, ValueError):
                continue
            if data.get("course") == course_id and data.get("input", {}).get("fingerprint") == fingerprint:
                return cls(manifest.parent)
        return None

    # --- manifest ------------------------------------------------------------------------

    def save(self) -> None:
        write_json(self.manifest_path, self.manifest)

    @property
    def media(self) -> Path:
        return Path(self.manifest["input"]["media"])

    @property
    def language(self) -> str:
        return self.manifest["language"]

    def check_media(self) -> None:
        """The original file must still be there and unchanged."""
        media = self.media
        if not media.exists():
            raise FileNotFoundError(f"input file is gone: {media}")
        if file_fingerprint(media) != self.manifest["input"]["fingerprint"]:
            raise RuntimeError(f"input file changed since the job was created: {media}")

    # --- slides ----------------------------------------------------------------------------

    SLIDE_SUFFIXES = (".pdf", ".pptx")

    @property
    def slides_dir(self) -> Path:
        return self.root / "slides"

    @property
    def slides(self) -> list[dict]:
        return self.manifest.setdefault("slides", [])

    def add_slides(self, paths: list[Path]) -> list[Path]:
        """Copy slide files into the job (originals untouched). Returns the newly added copies."""
        added = []
        known = {s["fingerprint"] for s in self.slides}
        for path in paths:
            path = path.resolve()
            if path.suffix.lower() not in self.SLIDE_SUFFIXES:
                raise ValueError(f"unsupported slide file {path.name}: use PDF or PPTX")
            fp = file_fingerprint(path)
            if fp in known:
                continue
            self.slides_dir.mkdir(parents=True, exist_ok=True)
            copy = self.slides_dir / f"{len(self.slides) + 1:02d}_{path.name}"
            shutil.copy2(path, copy)
            self.slides.append({"source": str(path), "file": copy.name, "fingerprint": fp})
            known.add(fp)
            added.append(copy)
        if added:
            self.save()
        return added

    # --- stages --------------------------------------------------------------------------

    def stage(self, name: str) -> dict[str, Any]:
        return self.manifest["stages"].get(name, {})

    def stage_done(self, name: str, input_hash: str) -> bool:
        st = self.stage(name)
        return st.get("status") == "done" and st.get("input_hash") == input_hash

    def mark_stage(self, name: str, status: str, input_hash: str | None = None, **info: Any) -> None:
        st = self.manifest["stages"].setdefault(name, {})
        st["status"] = status
        st["updated"] = datetime.now().isoformat(timespec="seconds")
        if input_hash is not None:
            st["input_hash"] = input_hash
        st.update(info)
        self.save()

    def invalidate(self, names: list[str]) -> None:
        for name in names:
            self.manifest["stages"].pop(name, None)
        self.save()

    # --- STT runs ------------------------------------------------------------------------

    @property
    def current_run(self) -> str | None:
        return self.manifest["stt"]["current_run"]

    def new_run(self, make_current: bool, **info: Any) -> str:
        runs = self.manifest["stt"]["runs"]
        run_id = f"r{len(runs) + 1}"
        while run_id in runs or (self.stt_dir / run_id).exists():
            run_id = f"r{int(run_id[1:]) + 1}"
        runs[run_id] = {"created": datetime.now().isoformat(timespec="seconds"), **info}
        if make_current:
            self.manifest["stt"]["current_run"] = run_id
        self.save()
        return run_id

    def run_info(self, run_id: str) -> dict[str, Any]:
        return self.manifest["stt"]["runs"][run_id]

    # --- paths ---------------------------------------------------------------------------

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def full_audio(self) -> Path:
        return self.audio_dir / "full.flac"

    @property
    def silences_path(self) -> Path:
        return self.audio_dir / "silences.json"

    @property
    def stt_dir(self) -> Path:
        return self.root / "stt"

    def run_dir(self, run_id: str) -> Path:
        return self.stt_dir / run_id

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    # --- locking and logging ---------------------------------------------------------------

    @contextmanager
    def lock(self) -> Iterator[None]:
        """Only one process may work on a job at a time."""
        with (self.root / ".lock").open("w") as fh:
            try:
                oscompat.lock(fh, blocking=False)
            except BlockingIOError:
                raise JobLockedError(f"another process is already working on {self.root}") from None
            try:
                yield
            finally:
                oscompat.unlock(fh)

    def logger(self) -> logging.Logger:
        log = logging.getLogger(f"lecture.job.{self.root.name}")
        if not log.handlers:
            handler = logging.FileHandler(self.root / "log.txt", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
            log.addHandler(handler)
            log.setLevel(logging.INFO)
            log.propagate = False
        return log
