"""Progress reporting, shared by the CLI and (later) the UI."""

from __future__ import annotations

import logging
from typing import Protocol


class Reporter(Protocol):
    def stage(self, name: str) -> None: ...
    def progress(self, done: float, total: float, text: str = "") -> None: ...
    def info(self, message: str) -> None: ...
    def warn(self, message: str) -> None: ...


class NullReporter:
    def stage(self, name: str) -> None:
        pass

    def progress(self, done: float, total: float, text: str = "") -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warn(self, message: str) -> None:
        pass


class LoggingReporter:
    """Forwards to another reporter and writes stage/info/warn lines to the job log."""

    def __init__(self, inner: Reporter, log: logging.Logger):
        self.inner = inner
        self.log = log

    def stage(self, name: str) -> None:
        self.log.info("stage %s", name)
        self.inner.stage(name)

    def progress(self, done: float, total: float, text: str = "") -> None:
        self.inner.progress(done, total, text)

    def info(self, message: str) -> None:
        self.log.info(message)
        self.inner.info(message)

    def warn(self, message: str) -> None:
        self.log.warning(message)
        self.inner.warn(message)
