"""The user's word lists, read and changed by the settings app.

Two kinds of words:
    my words      ~/.local/share/ats-ai/my_words.tsv, written by the user (thdee -> тэгэхдээ).
                  Used before the model, see personal.WordList.
    remembered    corrections learned while typing: a candidate picked, or
                  Latin kept with Esc. They come from the history file, see
                  personal.Personal.

A remembered word is forgotten by adding it to forgotten.tsv next to the
history file. The history itself is never rewritten: it is the record of
what was typed, and later training reads it.

Nothing here knows about Qt or IBus, so Linux and Windows share it.
"""

from pathlib import Path

from ats_ai.history import HISTORY

ROOT = Path(__file__).resolve().parent.parent
MY_WORDS = HISTORY.parent / "my_words.tsv"  # the program folder may be read-only (/opt)
FORGOTTEN = HISTORY.parent / "forgotten.tsv"

HEADER = "# Your own words, used before the model. One per line: latin<TAB>cyrillic\n"


def _rows(path):
    """(latin, cyrillic) rows of a latin<TAB>cyrillic file, comments skipped."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        row = [part.strip() for part in line.split("\t")]
        if len(row) == 2 and all(row):
            rows.append((row[0].lower(), row[1]))
    return rows


def clean(latin, cyrillic):
    """Checked (latin, cyrillic), or ValueError with a message for the user."""
    latin, cyrillic = latin.strip().lower(), cyrillic.strip()
    if not latin or not cyrillic:
        raise ValueError("Латин болон кирилл хоёулаа хэрэгтэй.")
    if any(c in latin + cyrillic for c in "\t\n\r"):
        raise ValueError("Таб болон шинэ мөр оруулж болохгүй.")
    if " " in latin:
        raise ValueError("Латин тал нь нэг үг байна (зайгүй).")
    return latin, cyrillic


def my_words(path=MY_WORDS):
    return _rows(path)


def save_my_words(rows, path=MY_WORDS):
    """Write the list back. Comment lines at the top of the file are kept."""
    try:
        old = path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError):
        old = []
    header = []
    for line in old:
        if not line.startswith("#"):
            break
        header.append(line if line.endswith("\n") else line + "\n")
    body = "".join(f"{latin}\t{cyrillic}\n" for latin, cyrillic in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(header or [HEADER]) + body, encoding="utf-8")
    tmp.replace(path)  # the engine never sees a half-written file


def add_my_word(latin, cyrillic, path=MY_WORDS):
    """Add or replace one word. Returns the cleaned (latin, cyrillic)."""
    latin, cyrillic = clean(latin, cyrillic)
    rows = [r for r in my_words(path) if r[0] != latin]
    save_my_words(rows + [(latin, cyrillic)], path)
    return latin, cyrillic


def remove_my_word(latin, path=MY_WORDS):
    save_my_words([r for r in my_words(path) if r[0] != latin], path)


def forgotten(path=FORGOTTEN):
    return set(_rows(path))


def remembered(history=HISTORY, forgotten_path=FORGOTTEN):
    """Corrections learned while typing, newest first: (latin, cyrillic, how).

    how is "picked" (another candidate chosen) or "latin" (kept with Esc).
    Undone and forgotten ones are left out.
    """
    from ats_ai.personal import Personal  # here to keep imports one-way

    personal = Personal(history, forgotten_path)
    hows, last = {}, {}
    try:
        for number, line in enumerate(history.read_text(encoding="utf-8").splitlines()):
            row = line.split("\t")
            if len(row) == 4 and row[3] in ("picked", "latin"):
                hows[(row[1], row[2])] = row[3]
                last[(row[1], row[2])] = number
    except (OSError, UnicodeDecodeError):
        pass
    out, seen = [], set()
    for latin, picks in personal.picks.items():
        dropped = personal.forgotten.get(latin)
        for _, cyrillic in reversed(picks):
            if cyrillic not in dropped and (latin, cyrillic) not in seen:
                seen.add((latin, cyrillic))
                out.append((latin, cyrillic, hows.get((latin, cyrillic), "picked")))
    out.sort(key=lambda r: -last.get((r[0], r[1]), -1))
    return out


def forget(latin, cyrillic, path=FORGOTTEN):
    """Stop using a remembered correction. The engine sees it on the next key."""
    rows = forgotten(path)
    rows.add((latin.lower(), cyrillic))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(f"{a}\t{b}\n" for a, b in sorted(rows)), encoding="utf-8")
    tmp.replace(path)


# --- Recent words, marked right or wrong ------------------------------------

LABELS = HISTORY.parent / "labels.tsv"
RECENT = 100


def recent(n=RECENT, history=HISTORY, labels_path=LABELS):
    """The last n typed words, newest first, with any mark already given.

    Each is a dict: line, context, latin, output, how, verdict, correct.
    Words taken back with Backspace (an "undone" row right after) are left out.
    """
    from ats_ai.personal import Labels

    try:
        lines = history.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    marks = Labels(labels_path).all()
    out = []
    skip = 0
    for number in range(len(lines) - 1, -1, -1):
        row = lines[number].split("\t")
        if len(row) != 4:
            continue
        context, latin, output, how = row
        if how == "undone":
            skip += 1
            continue
        if skip:
            skip -= 1
            continue
        mark = marks.get(number)
        out.append({
            "line": number, "context": context, "latin": latin, "output": output, "how": how,
            "verdict": mark[3] if mark else "", "correct": mark[4] if mark else "",
        })
        if len(out) == n:
            break
    return out


def mark(word, verdict, correct="", labels_path=LABELS):
    """Mark one recent word "ok" or "wrong" (with the correct word)."""
    if verdict not in ("ok", "wrong"):
        raise ValueError(verdict)
    if verdict == "wrong":
        correct = correct.strip()
        if not correct or any(c in correct for c in "\t\n\r"):
            raise ValueError("Зөв үгийг бичнэ үү.")
        if correct == word["output"]:
            raise ValueError("Зөв үг нь гарсантай ижил байна — «Зөв» гэж тэмдэглэнэ үү.")
    else:
        correct = ""
    labels_path.parent.mkdir(parents=True, exist_ok=True)
    with open(labels_path, "a", encoding="utf-8") as f:
        f.write("\t".join([str(word["line"]), word["context"], word["latin"],
                           word["output"], verdict, correct]) + "\n")
