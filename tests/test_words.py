"""ats_ai/words.py: the settings app's word lists."""

import pytest

from ats_ai import words
from ats_ai.personal import Personal


def test_add_replace_remove_keeps_header(tmp_path):
    path = tmp_path / "my_words.tsv"
    path.write_text("# my header\nbnu\tбайна уу\n", encoding="utf-8")
    words.add_my_word(" THdee ", " тэгэхдээ ", path)
    assert words.my_words(path) == [("bnu", "байна уу"), ("thdee", "тэгэхдээ")]
    words.add_my_word("bnu", "байна уу?", path)  # same Latin: replaced, not doubled
    assert words.my_words(path) == [("thdee", "тэгэхдээ"), ("bnu", "байна уу?")]
    words.remove_my_word("thdee", path)
    assert words.my_words(path) == [("bnu", "байна уу?")]
    assert path.read_text(encoding="utf-8").startswith("# my header\n")


@pytest.mark.parametrize("latin, cyrillic", [("", "а"), ("a", ""), ("two words", "а"), ("a\tb", "в")])
def test_bad_input_is_refused(tmp_path, latin, cyrillic):
    with pytest.raises(ValueError):
        words.add_my_word(latin, cyrillic, tmp_path / "w.tsv")


def history(tmp_path, *rows):
    path = tmp_path / "history.tsv"
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_remembered_and_forget(tmp_path):
    path = history(
        tmp_path,
        ("", "thdee", "thdee", "latin"),
        ("", "thdee", "thdee", "latin"),   # twice: remembered
        ("миний", "duu", "дүү", "picked"),
        ("", "al", "аль", "accepted"),   # not a correction
        ("", "sda", "sda", "latin"),
        ("", "sda", "sda", "undone"),   # cancelled right away
    )
    gone = tmp_path / "forgotten.tsv"
    # newest first
    assert words.remembered(path, gone) == [("duu", "дүү", "picked"), ("thdee", "thdee", "latin")]

    words.forget("thdee", "thdee", gone)
    assert words.remembered(path, gone) == [("duu", "дүү", "picked")]
    assert Personal(path, gone).best("", "thdee") is None   # the model decides again
    assert Personal(path, gone).best("миний", "duu") == "дүү"


def test_picking_again_unforgets(tmp_path):
    path = history(tmp_path, ("", "thdee", "thdee", "latin"), ("", "thdee", "thdee", "latin"))
    gone = tmp_path / "forgotten.tsv"
    words.forget("thdee", "thdee", gone)
    personal = Personal(path, gone)
    assert personal.best("", "thdee") is None
    personal.learn("", "thdee", "thdee", "latin")   # one Esc after forgetting: not yet
    assert personal.best("", "thdee") is None
    personal.learn("", "thdee", "thdee", "latin")   # second: Latin on purpose
    assert personal.best("", "thdee") == "thdee"
    assert words.forgotten(gone) == set()


def test_recent_newest_first_without_undone(tmp_path):
    path = history(
        tmp_path,
        ("", "bi", "би", "accepted"),
        ("би", "thdee", "түүхдээ", "accepted"),
        ("би", "thdee", "түүхдээ", "undone"),   # taken back: not shown
        ("би", "harij", "хариж", "accepted"),
    )
    labels = tmp_path / "labels.tsv"
    got = words.recent(10, path, labels)
    assert [(w["line"], w["latin"]) for w in got] == [(3, "harij"), (0, "bi")]
    assert got[0]["verdict"] == ""


def test_mark_and_fix_applies_while_typing(tmp_path):
    path = history(tmp_path, ("би одоо", "harij", "хариж", "accepted"))
    labels = tmp_path / "labels.tsv"
    word = words.recent(10, path, labels)[0]
    with pytest.raises(ValueError):
        words.mark(word, "wrong", "хариж", labels)   # same as the output
    words.mark(word, "wrong", "харьж", labels)
    again = words.recent(10, path, labels)[0]
    assert (again["verdict"], again["correct"]) == ("wrong", "харьж")
    p = Personal(path, tmp_path / "forgotten.tsv")
    assert p.best("одоо", "harij") == "харьж"
    words.mark(again, "ok", "", labels)               # changed my mind: last mark wins
    assert words.recent(10, path, labels)[0]["verdict"] == "ok"
    assert Personal(path, tmp_path / "forgotten.tsv").best("одоо", "harij") is None
