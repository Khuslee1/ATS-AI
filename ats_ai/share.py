"""Export what a tester typed, for training, after they have looked at it.

Nothing is sent anywhere: the settings app writes a file and the tester
hands it over themselves. Before that:
    - rows that look private are left out on their own: three or more digits
      in a row (phone, card, code), an e-mail, a web address;
    - the tester sees every remaining row and can remove any of them;
    - a tester code is used instead of a name.

The file is TSV with a short # header, then one word per line:
    context<TAB>latin<TAB>output<TAB>how<TAB>verdict<TAB>correct
how is accepted/picked/latin/undone (see history.py), verdict ok/wrong/""
from the «Сүүлийн бичсэн» tab, correct the right word for a wrong one.

settings.json "shared_upto" remembers the last history line exported, so
the next export starts after it.
"""

import re
from datetime import date

from ats_ai.history import HISTORY
from ats_ai.personal import Labels

PRIVATE = re.compile(r"\d{3,}|@|https?:|www\.|\.(com|mn|org|net)\b", re.IGNORECASE)
CODE = re.compile(r"^[a-z0-9_-]{1,20}$")
COLUMNS = ("context", "latin", "output", "how", "verdict", "correct")


def private(*texts):
    return any(PRIVATE.search(t) for t in texts if t)


def rows(start=0, history=HISTORY, labels_path=None):
    """(rows, dropped, end) of the history from line `start` on.

    Each row is a dict with "line" and COLUMNS. dropped counts the rows left
    out because they looked private; end is the line the next export starts
    from (rows removed by hand are not offered again either).
    """
    labels = Labels(labels_path or history.parent / "labels.tsv").all()
    try:
        lines = history.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return [], 0, start
    if start > len(lines):  # the history was cleared since the last export
        start = 0
    out, dropped = [], 0
    for number in range(start, len(lines)):
        row = lines[number].split("\t")
        if len(row) != 4:
            continue
        context, latin, output, how = row
        mark = labels.get(number)
        verdict, correct = (mark[3], mark[4]) if mark else ("", "")
        if private(context, latin, output, correct):
            dropped += 1
            continue
        out.append({"line": number, "context": context, "latin": latin, "output": output,
                    "how": how, "verdict": verdict, "correct": correct})
    return out, dropped, len(lines)


def file_name(code, today=None):
    return f"ats-ai-{code}-{(today or date.today()).isoformat()}.tsv"


def write(path, code, rows, model=""):
    """Write the export file."""
    if not CODE.match(code):
        raise ValueError("Туршигчийн код: латин жижиг үсэг, тоо, - эсвэл _ (ж: tester03).")
    if not rows:
        raise ValueError("Хуваалцах мөр алга.")
    header = (
        f"# ATS-AI export · tester {code} · {date.today().isoformat()} · model {model}\n"
        "# " + "\t".join(COLUMNS) + "\n"
    )
    body = "".join("\t".join(r[c] for c in COLUMNS) + "\n" for r in rows)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(header + body, encoding="utf-8")
    tmp.replace(path)
