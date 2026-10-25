"""Setup panel writes: settings.yaml layer, keys in .env, courses, folders."""

import stat

import pytest

from lecture import config as cfgmod
from lecture import settings


@pytest.fixture
def conf_dir(xdg, tmp_path):
    xdg.mkdir(parents=True)
    (xdg / "config.yaml").write_text(f"# my own comment\npaths:\n  jobs_dir: {tmp_path / 'jobs'}\n")
    (tmp_path / "jobs").mkdir()
    return xdg


def test_notes_model_goes_first_with_one_fallback_per_other_provider(conf_dir):
    settings.set_notes_model("claude:claude-haiku-5-5")
    chain = cfgmod.load_config().llm.tasks["notes"]
    assert chain[0] == "claude:claude-haiku-5-5"
    assert [c.split(":")[0] for c in chain] == ["claude", "gemini", "groq"]  # Sonnet isn't a fallback for Haiku
    settings.set_notes_model("gemini:gemini-3.8-flash")
    assert cfgmod.load_config().llm.tasks["notes"][:2] == ["gemini:gemini-3.8-flash", "claude:claude-sonnet-5-5"]
    assert "# my own comment" in (conf_dir / "config.yaml").read_text()  # the user's file untouched


def test_stt_mode_outputs_and_rollback(conf_dir):
    settings.set_stt_mode("cloud")
    settings.set_outputs({"quiz": True})
    conf = cfgmod.load_config()
    assert conf.stt.providers == ["groq"] and conf.notes.outputs.quiz and not conf.notes.outputs.flashcards
    with pytest.raises(ValueError):
        settings.set_stt_mode("carrier pigeon")
    before = cfgmod.settings_path().read_text()
    with pytest.raises(Exception):
        settings.update_settings({"chunking": {"target_s": 5}})  # invalid (min 60): rolled back
    assert cfgmod.settings_path().read_text() == before and cfgmod.load_config().chunking.target_s >= 60


def test_keys_written_private_and_comments_kept(conf_dir):
    env = conf_dir / ".env"
    env.write_text("# keys\nGROQ_API_KEY=\n")
    assert settings.key_status() == {"groq": False, "gemini": False, "mac": False}
    settings.set_key("gemini", "AIzaSyTESTKEY1234567890")
    assert settings.key_status() == {"groq": False, "gemini": True, "mac": False}
    assert env.read_text().startswith("# keys") and stat.S_IMODE(env.stat().st_mode) == 0o600
    with pytest.raises(ValueError):
        settings.set_key("gemini", "not a key; rm -rf")


def test_courses_add_edit_delete(conf_dir):
    c = settings.save_course({"name": "Elektrische energie en aandrijvingen", "language": "nl",
                              "lecturer": "Jan Example", "extra_terms": ["HVDC", " "]})
    assert c.id == "elektrische-energie-en-aandrijvingen" and c.extra_terms == ["HVDC"]
    ids = [x.id for x in cfgmod.load_courses()]
    assert "digitale-elektronica" in ids and c.id in ids  # copied from the repo list, then added
    settings.save_course({"id": c.id, "name": "EEA", "language": "nl"})
    assert next(x for x in cfgmod.load_courses() if x.id == c.id).name == "EEA"
    settings.delete_course(c.id)
    assert c.id not in [x.id for x in cfgmod.load_courses()]
    with pytest.raises(Exception):
        settings.save_course({"name": "Bad", "language": "fr"})


def test_folders(conf_dir):
    assert settings.folders() == {"folders": [], "assign": {}}
    data = settings.save_folders({"folders": [{"id": "f1", "name": "Examen januari"}],
                                  "assign": {"2026-02-26_dep_les-4": "f1", "../evil": "f1", "x": "nope"}})
    assert data["assign"] == {"2026-02-26_dep_les-4": "f1"}
    with pytest.raises(ValueError):
        settings.save_folders({"folders": [{"id": "a", "name": "X"}, {"id": "b", "name": "x"}]})
