import os
import stat

import pytest
from pydantic import ValidationError

from lecture import config as cfg
from lecture.doctor import check_env_file, describe_gemini_error


def test_deep_merge_nested_and_replace():
    base = {"a": {"x": 1, "y": 2}, "b": [1, 2]}
    out = cfg.deep_merge(base, {"a": {"y": 3}, "b": [9]})
    assert out == {"a": {"x": 1, "y": 3}, "b": [9]}
    assert base["a"]["y"] == 2  # base not mutated


def test_repo_defaults_load(xdg):
    conf = cfg.load_config()
    assert conf.stt.model == "whisper-large-v3"
    assert conf.paths.jobs_dir.is_absolute()  # ~ expanded
    assert {"algemene-economie", "data-science"} <= {c.id for c in cfg.load_courses()}


def test_user_override_is_merged(xdg):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text("limits:\n  gemini:\n    requests_per_day: 250\n")
    conf = cfg.load_config()
    assert conf.limits.gemini.requests_per_day == 250
    assert conf.limits.gemini.requests_per_minute == 10  # untouched default


def test_typo_in_override_is_rejected(xdg):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text("stt:\n  modle: whisper-large-v3-turbo\n")
    with pytest.raises(ValidationError):
        cfg.load_config()


def test_bad_task_chain_is_rejected(xdg):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text("llm:\n  tasks:\n    cleanup: ['gemini-flash-latest']\n")
    with pytest.raises(ValidationError):
        cfg.load_config()


def test_keys_from_env_file_and_environment(xdg, monkeypatch):
    xdg.mkdir(parents=True)
    (xdg / ".env").write_text("GROQ_API_KEY=from-file\nGEMINI_API_KEY= spaced \n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    keys = cfg.load_keys()
    assert keys == {"GROQ_API_KEY": "from-file", "GEMINI_API_KEY": "spaced", "OPENROUTER_API_KEY": "from-env",
                    "LECTURE_MAC_TOKEN": "", "LECTURE_HUB_CODE": ""}


def test_env_file_permissions(xdg):
    xdg.mkdir(parents=True)
    env = xdg / ".env"
    env.write_text("")
    os.chmod(env, 0o644)
    assert [c.status for c in check_env_file()] == ["warn"]
    os.chmod(env, stat.S_IRUSR | stat.S_IWUSR)
    assert [c.status for c in check_env_file()] == ["ok"]


class _FakeGeminiError:
    code = 429
    status = "RESOURCE_EXHAUSTED"
    message = "You exceeded your current quota."
    details = {"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "35s"},
    ]}}


def test_gemini_429_shows_quota_and_retry():
    text = describe_gemini_error(_FakeGeminiError())
    assert "GenerateRequestsPerDayPerProjectPerModel-FreeTier = 20" in text
    assert "retry after 35s" in text
