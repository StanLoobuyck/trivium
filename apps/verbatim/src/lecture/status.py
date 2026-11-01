"""Machine status for `lecture status` and the UI: worker, queue, GPU, free-quota usage, Claude calls."""

from __future__ import annotations

import shutil
from pathlib import Path
import subprocess
from collections import Counter
from typing import Any

from . import config as cfgmod
from .config import Config
from .queue import Queue, worker_running
from .ratelimit import DAY_S, Ledger, Window, groq_stt_windows


def nvidia_smi_problem(text: str) -> str:
    """nvidia-smi prints its errors on stdout; explain the common one after a driver update."""
    text = " ".join(text.split())[:160]
    if "version mismatch" in text.lower():
        return f"GPU unusable until reboot (NVIDIA driver updated; {text}) — Groq is used meanwhile"
    return f"nvidia-smi failed: {text or 'no output'}"


def nvidia_power_state() -> str | None:
    """Runtime power state of the NVIDIA GPU from sysfs ('suspended', 'active'), None if it isn't on the
    PCI bus (e.g. integrated-only graphics mode). Reading sysfs never wakes the GPU; nvidia-smi does."""
    for dev in Path("/sys/bus/pci/devices").glob("*"):
        try:
            if (dev / "vendor").read_text().strip() == "0x10de" and (dev / "class").read_text().startswith("0x03"):
                return (dev / "power" / "runtime_status").read_text().strip()
        except OSError:
            continue
    return None


POWER_SUPPLY = Path("/sys/class/power_supply")  # tests point this elsewhere


def on_battery(root: Path | None = None) -> bool:
    """True if the laptop runs on its battery: a battery is discharging and no charger (Mains or USB-C) is
    online. Unknown (desktop, no sysfs) counts as on power."""
    def read(dev: Path, name: str) -> str:
        try:
            return (dev / name).read_text().strip()
        except OSError:
            return ""
    devs = list((root or POWER_SUPPLY).glob("*"))
    if any(read(d, "type") != "Battery" and read(d, "online") == "1" for d in devs):
        return False
    return any(read(d, "type") == "Battery" and read(d, "status") == "Discharging" for d in devs)


def gpu() -> str:
    if not shutil.which("nvidia-smi"):
        return "no NVIDIA GPU (Groq is used)"
    state = nvidia_power_state()
    if state is None:
        return "no NVIDIA GPU visible (integrated graphics mode?)"
    if state == "suspended":
        return "NVIDIA GPU asleep (not woken to check)"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"nvidia-smi failed: {exc}"
    if out.returncode != 0:
        return nvidia_smi_problem(out.stdout + out.stderr)
    name, used, total, util = [x.strip() for x in out.stdout.splitlines()[0].split(",")]
    return f"{name}: {used}/{total} MiB, {util}% busy"


def gather(conf: Config, queue: Queue | None = None) -> dict[str, Any]:
    queue = queue or Queue()
    snap = queue.snapshot()
    ledger = Ledger(cfgmod.cache_dir() / "ledger.json")
    lim = conf.limits.gemini
    gemini_models = sorted({e.split(":", 1)[1] for e in conf.llm.tasks["notes"] if e.startswith("gemini:")})
    quotas = {"Groq speech-to-text": ledger.usage("groq_stt", groq_stt_windows(conf.limits.groq_stt)),
              "Claude notes": ledger.usage("claude", [Window("calls/day", DAY_S,
                                                             conf.notes.max_claude_calls_per_day, "requests")])}
    for m in gemini_models:
        quotas[f"Gemini {m}"] = ledger.usage(f"gemini:{m}", [Window("requests/day", DAY_S, lim.requests_per_day,
                                                                     "requests")])
    nxt = queue.next_notes_time(conf)
    return {"worker": worker_running(), "notes_paused": snap["notes_paused"],
            "queue": dict(Counter(i["status"] for i in snap["items"])),
            "next_notes": nxt.isoformat(timespec="minutes") if nxt else None,
            "gpu": gpu(), "quotas": quotas, "notes_schedule": conf.notes.schedule, "tonight": conf.notes.tonight}


def text(st: dict[str, Any]) -> list[str]:
    rows = [("Worker", "running" if st["worker"] else "not running (start: lecture worker, or the service)"),
            ("Queue", ", ".join(f"{n} {k}" for k, n in st["queue"].items()) or "empty"),
            ("Notes", f"{'PAUSED' if st['notes_paused'] else 'active'}; Claude allowed: {st['notes_schedule']}; "
                      f"'tonight' = {st['tonight']}" + (f"; next notes {st['next_notes']}" if st["next_notes"] else "")),
            ("GPU", st["gpu"])]
    rows += [(name, ", ".join(f"{w} {used:.0f}/{limit:.0f}" for w, (used, limit) in windows.items()))
             for name, windows in st["quotas"].items()]
    width = max(len(name) for name, _ in rows) + 2
    return [f"{name + ':':<{width}}{value}" for name, value in rows]
