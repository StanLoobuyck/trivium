"""Every frontend JS file must parse: one broken string in i18n.js once left the whole UI blank (2026-10-20)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "src" / "lecture" / "web"
FILES = sorted(WEB.rglob("*.js"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(WEB)) for p in FILES])
def test_js_parses(path):
    # ES modules (web/js/) need --input-type=module semantics: check them as .mjs via stdin
    is_module = "js" in path.relative_to(WEB).parts[:-1]
    cmd = ["node", "--check", "--input-type=module"] if is_module else ["node", "--check", str(path)]
    r = subprocess.run(cmd, input=path.read_text() if is_module else None, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_every_pipeline_stage_has_a_label_in_both_languages():
    from pathlib import Path

    text = (Path(__file__).parents[1] / "src/lecture/web/i18n.js").read_text(encoding="utf-8")
    for stage in ("audio", "transcribe", "sections", "notes", "suggestions"):
        assert text.count(f"stage_{stage}:") == 2, stage
