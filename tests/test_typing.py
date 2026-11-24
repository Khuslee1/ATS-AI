"""ats_ai/typing.py with a fake model (no torch)."""

from ats_ai.config import Config
from ats_ai.typing import Typing, match_case


def fake(context, latin):
    table = {
        "duu": [("дуу", 0.6), ("дүү", 0.3), ("дөө", 0.001)],
        "sain": [("сайн", 0.99)],
        "bn": [("бн", 0.9)],
    }
    return table.get(latin, [(latin, 1.0)])


def typing(tmp_path):
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    (root / "data" / "abbreviations.tsv").write_text("bn\tбайна\n", encoding="utf-8")
    history = tmp_path / "share" / "history.tsv"
    history.parent.mkdir()
    return Typing(fake, root=root, history=history), root, history


def test_options_order_and_case(tmp_path):
    t, root, _ = typing(tmp_path)
    assert t.options("", "duu") == ["дуу", "дүү"]          # дөө too unlikely to show
    assert t.options("", "Sain") == ["Сайн"]
    assert t.options("", "bn") == ["байна", "бн"]           # abbreviation first
    (tmp_path / "share" / "my_words.tsv").write_text("duu\tдүү\n", encoding="utf-8")
    assert t.options("", "duu") == ["дүү"]                  # my words are final
    assert t.options("", "") == []


def test_commit_learns_and_undo_forgets(tmp_path):
    t, _, history = typing(tmp_path)
    t.commit("миний", "duu", "дүү", "picked")
    assert t.options("миний", "duu")[0] == "дүү"
    t.undo("миний", "duu", "дүү", "picked")
    assert t.options("миний", "duu")[0] == "дуу"
    assert [l.split("\t")[3] for l in history.read_text(encoding="utf-8").splitlines()] == ["picked", "undone"]


def test_paused_saves_nothing(tmp_path):
    t, _, history = typing(tmp_path)
    Config(history.parent / "settings.json").save(paused=True)
    t.commit("", "duu", "дүү", "picked")
    assert not history.exists()


def test_match_case():
    assert match_case("TSAI", "цай") == "ЦАЙ"
    assert match_case("t", "т") == "т"
