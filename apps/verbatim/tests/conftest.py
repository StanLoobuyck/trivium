import subprocess
from pathlib import Path

import pytest

from lecture import config as cfg


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    """Isolate XDG config/cache dirs and API keys from the user's real ones."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    for name in cfg.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "xdg-config" / cfg.APP_NAME


@pytest.fixture
def conf(xdg):
    return cfg.load_config()


def make_audio(path: Path, pattern: list[tuple[str, float]], video: bool = False) -> Path:
    """Synthetic 'lecture': ('tone', seconds) bursts and ('quiet', seconds) gaps with faint noise."""
    parts = []
    for kind, seconds in pattern:
        if kind == "tone":
            parts.append(f"sine=frequency=300:duration={seconds}:sample_rate=16000")
        else:
            parts.append(f"anoisesrc=color=pink:amplitude=0.001:duration={seconds}:sample_rate=16000")
    inputs = []
    for p in parts:
        inputs += ["-f", "lavfi", "-i", p]
    n = len(parts)
    concat = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *inputs]
    if video:
        total = sum(s for _, s in pattern)
        cmd += ["-f", "lavfi", "-i", f"color=c=gray:s=160x90:d={total}:r=5"]
    cmd += ["-filter_complex", concat, "-map", "[a]"]
    if video:
        cmd += ["-map", f"{n}:v", "-c:v", "libx264", "-preset", "ultrafast", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(autouse=True)
def on_power(tmp_path_factory, monkeypatch):
    """Tests never depend on whether the laptop's charger is plugged in (status.on_battery reads sysfs)."""
    from lecture import status

    monkeypatch.setattr(status, "POWER_SUPPLY", tmp_path_factory.mktemp("power_supply"))


@pytest.fixture(autouse=True)
def no_inbox(monkeypatch):
    """The worker scans the watch folder; the repo config points it at the user's real ~/Lectures/inbox.
    Off in every test; tests/test_inbox.py calls the real functions with a temporary folder."""
    from lecture import inbox

    real = inbox.tick
    monkeypatch.setattr(inbox, "tick", lambda *a, **k: [])
    return real
