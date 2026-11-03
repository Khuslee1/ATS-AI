import os

from ats_ai.personal import Personal, WordList


def personal(tmp_path, *rows):
    path = tmp_path / "history.tsv"
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    return Personal(path)


def test_missing_file_means_no_corrections(tmp_path):
    assert Personal(tmp_path / "none.tsv").best("", "uur") is None


def test_one_correction_applies_everywhere(tmp_path):
    p = personal(tmp_path, ("", "uur", "өөр", "picked"))
    assert p.best("хэн нэг", "uur") == "өөр"


def test_esc_teaches_keeping_latin(tmp_path):
    p = personal(tmp_path, ("", "git", "git", "latin"))
    assert p.best("", "git") == "git"


def test_accepted_words_teach_nothing(tmp_path):
    p = personal(tmp_path, ("", "ats", "ац", "accepted"))
    assert p.best("", "ats") is None


def test_conflicting_corrections_depend_on_previous_word(tmp_path):
    p = personal(
        tmp_path,
        ("сайн", "uu", "уу", "picked"),
        ("зөв", "uu", "үү", "picked"),
    )
    assert p.best("сайн", "uu") == "уу"
    assert p.best("зөв", "uu") == "үү"
    assert p.best("хурдан", "uu") is None


def test_undone_cancels_the_correction(tmp_path):
    p = personal(
        tmp_path,
        ("", "ajillahgui", "ажиллах", "picked"),
        ("", "ajillahgui", "ажиллах", "undone"),
    )
    assert p.best("", "ajillahgui") is None


def test_undone_on_an_accepted_word_changes_nothing(tmp_path):
    p = personal(
        tmp_path,
        ("", "uur", "өөр", "picked"),
        ("", "uur", "уур", "undone"),
    )
    assert p.best("", "uur") == "өөр"


def word_list(tmp_path, text):
    path = tmp_path / "words.tsv"
    path.write_text(text, encoding="utf-8")
    return path, WordList(path)


def test_word_list_reads_several_meanings(tmp_path):
    _, words = word_list(tmp_path, "# note\nBNU\tбайна уу\nats\tATS\nym\tюм\nym\tямар\n")
    assert words.get("bnu") == ["байна уу"]
    assert words.get("ats") == ["ATS"]
    assert words.get("ym") == ["юм", "ямар"]
    assert words.get("none") == []


def test_word_list_skips_bad_lines(tmp_path):
    _, words = word_list(tmp_path, "bnu байна уу\na\tb\tc\n\t\nok\tза\n")
    assert words.get("bnu") == []
    assert words.get("ok") == ["за"]


def test_word_list_sees_edits_without_restart(tmp_path):
    path, words = word_list(tmp_path, "a\tа\n")
    assert words.get("a") == ["а"]
    path.write_text("a\tя\n", encoding="utf-8")
    os.utime(path, (1, 1))
    assert words.get("a") == ["я"]


def test_word_list_survives_a_missing_file(tmp_path):
    path, words = word_list(tmp_path, "a\tа\n")
    assert words.get("a") == ["а"]
    path.unlink()
    assert words.get("a") == []
