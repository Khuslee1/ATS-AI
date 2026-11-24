"""ats_ai/share.py: tester export."""

from datetime import date

import pytest

from ats_ai import share


def history(tmp_path, *rows):
    path = tmp_path / "history.tsv"
    path.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_private_rows_are_left_out(tmp_path):
    path = history(
        tmp_path,
        ("", "sain", "сайн", "accepted"),
        ("утас", "99112233", "99112233", "latin"),
        ("", "bat@gmail.com", "bat@gmail.com", "latin"),
        ("", "https://x.mn", "https://x.mn", "latin"),
        ("", "8", "8", "accepted"),                      # one digit is fine
    )
    rows, dropped, end = share.rows(0, path)
    assert [r["latin"] for r in rows] == ["sain", "8"]
    assert (dropped, end) == (3, 5)


def test_labels_go_along_and_start_skips_shared(tmp_path):
    path = history(tmp_path, ("", "bi", "би", "accepted"), ("би", "harij", "хариж", "accepted"))
    (tmp_path / "labels.tsv").write_text("1\tби\tharij\tхариж\twrong\tхарьж\n", encoding="utf-8")
    rows, _, _ = share.rows(0, path)
    assert (rows[1]["verdict"], rows[1]["correct"]) == ("wrong", "харьж")
    rows, _, _ = share.rows(1, path)
    assert [r["latin"] for r in rows] == ["harij"]
    assert share.rows(99, path)[0][0]["latin"] == "bi"   # history cleared: start over


def test_write_checks_code_and_writes_tsv(tmp_path):
    rows, _, _ = share.rows(0, history(tmp_path, ("", "bi", "би", "accepted")))
    out = tmp_path / share.file_name("tester03", date(2026, 11, 24))
    assert out.name == "ats-ai-tester03-2026-11-24.tsv"
    with pytest.raises(ValueError):
        share.write(out, "Бат Болд", rows)
    with pytest.raises(ValueError):
        share.write(out, "tester03", [])
    share.write(out, "tester03", rows, "v4.pt")
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ATS-AI export · tester tester03")
    assert lines[2] == "\tbi\tби\taccepted\t\t"
