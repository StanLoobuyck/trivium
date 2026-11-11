"""Welcome steps (simple mode): key test with the service, empty course list, finishing once."""

import httpx
import pytest

from lecture import config as cfgmod
from lecture import settings


@pytest.fixture
def simple(xdg, tmp_path):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(f"app:\n  simple: true\npaths:\n  jobs_dir: {tmp_path / 'jobs'}\n")
    return xdg


def fake(status: int, text: str = "{}", fail: bool = False):
    seen = []

    class Client:
        def get(self, url, headers, timeout):
            seen.append((url, headers))
            if fail:
                raise httpx.ConnectError("no network")
            return httpx.Response(status, text=text)

    return Client(), seen


KEY = "gsk_" + "a" * 40


def test_working_key_is_saved(simple):
    client, seen = fake(200)
    assert settings.test_key("groq", f"  {KEY} ", client) == {"ok": True, "reason": "ok"}
    assert seen == [("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {KEY}"})]
    assert settings.key_status()["groq"] is True


@pytest.mark.parametrize("status,text,reason", [
    (401, '{"error": "invalid_api_key"}', "rejected"),
    (400, '{"error": {"message": "User location is not supported for the API use."}}', "location"),
    (500, "oops", "error"),
])
def test_failing_key_is_not_saved(simple, status, text, reason):
    client, _ = fake(status, text)
    assert settings.test_key("gemini", "AIza" + "b" * 35, client)["reason"] == reason
    assert settings.key_status()["gemini"] is False


def test_no_network_and_bad_format(simple):
    client, seen = fake(200, fail=True)
    assert settings.test_key("groq", KEY, client)["reason"] == "offline"
    assert settings.test_key("groq", "not a key!", client)["reason"] == "format"
    assert len(seen) == 1  # a bad format is never sent


def test_new_user_in_simple_mode_starts_without_courses(simple):
    assert cfgmod.load_courses() == []
    settings.save_course({"id": None, "name": "Strafrecht", "language": "nl"})
    assert [c.name for c in cfgmod.load_courses()] == ["Strafrecht"]


def test_example_courses_outside_simple_mode(xdg):
    assert cfgmod.courses_file() == cfgmod.REPO_DIR / "courses.yaml"


def test_welcome_is_finished_once(simple):
    assert cfgmod.load_config().app.welcomed is False
    settings.finish_welcome()
    assert cfgmod.load_config().app.welcomed is True


def test_setup_simple_sets_the_defaults_and_keeps_the_rest(xdg, tmp_path):
    settings.setup_simple(tmp_path / "Mijn lessen")
    settings.set_key("groq", KEY)
    settings.finish_welcome()
    settings.setup_simple(tmp_path / "Mijn lessen")  # an update runs it again
    conf = cfgmod.load_config()
    assert conf.app.simple and conf.app.welcomed
    assert conf.stt.providers == ["groq", "local"] and conf.stt.local.skip_on_battery is False
    assert conf.stt.local.device == "auto" and conf.stt.local.model == "large-v3-turbo"
    assert conf.termfix.enabled is False
    assert conf.paths.jobs_dir == (tmp_path / "Mijn lessen" / "jobs").resolve()
    assert settings.key_status()["groq"] is True
    assert cfgmod.load_courses() == []


def test_setup_simple_fast_whisper_and_bad_choice(xdg, tmp_path):
    settings.setup_simple(tmp_path / "L", "fast")
    assert cfgmod.load_config().stt.local.model == "small"
    with pytest.raises(ValueError):
        settings.setup_simple(tmp_path / "L", "huge")
