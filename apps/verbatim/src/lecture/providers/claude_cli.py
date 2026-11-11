"""Notes via Claude Code headless (`claude -p`) on the user's Claude subscription.

Output contract (checked on Claude Code 2.1.302, pinned in tests/fixtures/claude_cli/):
`--output-format json` prints one JSON object with `type: "result"`, `is_error`, `result` (text) and, with
`--json-schema`, `structured_output` (the parsed object). Not logged in → exit 1, `is_error: true`,
`result: "Not logged in · Please run /login"` (note: `subtype` still says "success").

Calls run in an empty working directory with `--setting-sources project` so the user's own CLAUDE.md,
memory and MCP servers don't leak into the notes (measured: the global CLAUDE.md was in context otherwise).
Limits are shared with the user's own Claude use: a schedule and a daily call cap (ledger) guard them.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timedelta
from typing import Any

from .. import config as cfgmod
from ..config import Config
from ..ratelimit import DAY_S, Ledger, QuotaExhausted, Window
from ..report import NullReporter, Reporter
from ..util import find_claude
from .llm import LLMBadOutput, LLMLimit, LLMResult, LLMUnavailable

_LIMIT = re.compile(r"usage limit|rate limit|limit reached|quota|too many requests|overloaded", re.I)
_LOGIN = re.compile(r"not logged in|/login|authenticat|invalid api key|oauth", re.I)


def schedule_allows(schedule: str, now: datetime) -> tuple[bool, datetime | None]:
    """'always', or comma-separated windows like '22:00-08:00'. Returns (allowed, next window start)."""
    if schedule.strip() == "always":
        return True, None
    starts = []
    for part in schedule.split(","):
        a, b = (datetime.strptime(x.strip(), "%H:%M").time() for x in part.split("-"))
        t = now.time()
        inside = a <= t < b if a < b else (t >= a or t < b)  # window across midnight
        if inside:
            return True, None
        start = now.replace(hour=a.hour, minute=a.minute, second=0, microsecond=0)
        starts.append(start if start > now else start + timedelta(days=1))
    return False, min(starts)


class ClaudeCLI:
    name = "claude"

    def __init__(self, conf: Config, model: str, reporter: Reporter | None = None, ledger: Ledger | None = None,
                 clock=datetime.now):
        self.conf = conf
        self.model = model
        self.reporter = reporter or NullReporter()
        self.ledger = ledger or Ledger(cfgmod.cache_dir() / "ledger.json")
        self.clock = clock
        self.exe = find_claude()
        if not self.exe:
            raise LLMUnavailable("Claude Code (`claude`) not found on PATH")
        self.workdir = cfgmod.cache_dir() / "claude-workdir"  # empty: no project CLAUDE.md is discovered

    def command(self, system: str, schema: dict[str, Any]) -> list[str]:
        return [self.exe, "-p", "--output-format", "json", "--json-schema", json.dumps(schema),
                "--tools", "", "--no-session-persistence", "--setting-sources", "project", "--strict-mcp-config",
                "--model", self.model, "--system-prompt", system]

    def _check_budget(self) -> str:
        allowed, next_start = schedule_allows(self.conf.notes.schedule, self.clock())
        if not allowed:
            raise LLMLimit(f"notes schedule '{self.conf.notes.schedule}' doesn't allow Claude now", next_start)
        window = Window("calls/day", DAY_S, self.conf.notes.max_claude_calls_per_day, "requests")
        try:
            return self.ledger.reserve("claude", [window], {"requests": 1}, max_wait_s=0, label="Claude")
        except QuotaExhausted as exc:
            raise LLMLimit(str(exc), exc.resume_at) from exc

    def generate(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        event = self._check_budget()
        self.workdir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        try:
            proc = subprocess.run(self.command(system, schema), input=user, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  cwd=self.workdir, timeout=self.conf.notes.timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise LLMBadOutput(f"claude -p took longer than {self.conf.notes.timeout_s:.0f} s") from exc
        return parse_output(proc.stdout, proc.stderr, proc.returncode, time.time() - t0, self.model,
                            on_not_counted=lambda: self.ledger.release(event))


def parse_output(stdout: str, stderr: str, returncode: int, elapsed: float, model: str,
                 on_not_counted=lambda: None) -> LLMResult:
    """Interpret `claude -p --output-format json` output (pure function: tested on saved real outputs)."""
    try:
        out = json.loads(stdout)
    except json.JSONDecodeError:
        on_not_counted()
        text = (stderr or stdout).strip()[:300]
        if _LOGIN.search(text):
            raise LLMUnavailable(f"Claude Code is not logged in: {text}") from None
        raise LLMBadOutput(f"claude -p exit {returncode}, no JSON output: {text}") from None
    message = str(out.get("result") or "")
    if out.get("is_error") or returncode != 0:
        if _LOGIN.search(message):
            on_not_counted()
            raise LLMUnavailable(f"Claude Code is not logged in ({message}) — run `claude` once and /login")
        if out.get("api_error_status") == 429 or _LIMIT.search(message):
            raise LLMLimit(f"Claude usage limit: {message[:200]}")
        raise LLMBadOutput(f"claude -p error ({out.get('terminal_reason')}): {message[:300]}")
    data = out.get("structured_output")
    if data is None:  # older versions: the JSON is only in `result`
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            raise LLMBadOutput(f"no structured output in the answer: {message[:200]}") from None
    usage = out.get("usage", {})
    models = list(out.get("modelUsage", {}))
    return LLMResult(
        data=data, model=models[0] if models else model,
        input_tokens=usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0), elapsed_s=round(elapsed, 1),
        raw={k: out.get(k) for k in ("session_id", "num_turns", "stop_reason", "terminal_reason", "duration_ms",
                                     "total_cost_usd", "modelUsage")},
    )
