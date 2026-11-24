"""ats_ai/config.py and the settings it controls."""

from ats_ai.config import DEFAULTS, Config, models
from ats_ai.personal import Personal


def test_missing_or_broken_file_means_defaults(tmp_path):
    path = tmp_path / "settings.json"
    assert Config(path).get("model") == DEFAULTS["model"]
    path.write_text("{not json", encoding="utf-8")
    assert Config(path).get("escapes") == 2
    path.write_text('{"escapes": 7, "paused": true}', encoding="utf-8")
    config = Config(path)
    assert (config.get("escapes"), config.get("paused")) == (2, True)


def test_save_is_seen_by_another_reader(tmp_path):
    path = tmp_path / "settings.json"
    app, engine = Config(path), Config(path)
    assert engine.get("paused") is False
    app.save(paused=True, model="v3.pt", unknown="x")
    assert (engine.get("paused"), engine.get("model")) == (True, "v3.pt")
    assert "unknown" not in path.read_text(encoding="utf-8")


def history(tmp_path, *rows):
    path = tmp_path / "history.tsv"
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_escape_count_follows_the_setting(tmp_path):
    path = history(tmp_path, ("", "git", "git", "latin"))
    settings = tmp_path / "settings.json"
    assert Personal(path).best("", "git") is None            # default: 2
    Config(settings).save(escapes=1)
    assert Personal(path).best("", "git") == "git"
    Config(settings).save(escapes=0)                          # never
    p = Personal(history(tmp_path, *[("", "git", "git", "latin")] * 5))
    assert p.best("", "git") is None
    p.learn("", "git", "git", "latin")
    assert p.best("", "git") is None


def test_models_newest_first_without_checkpoints(tmp_path):
    for name in ("v2.pt", "v4.pt", "v4.pt.last"):
        (tmp_path / name).write_bytes(b"")
    import os
    os.utime(tmp_path / "v2.pt", (1, 1))
    assert [p.name for p in models(tmp_path)] == ["v4.pt", "v2.pt"]
