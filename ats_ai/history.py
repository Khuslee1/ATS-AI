"""What the user typed and kept, for the model to learn from later.

One row per word: context<TAB>latin<TAB>cyrillic<TAB>how, where how is
    accepted   the first suggestion was kept
    picked     another candidate was chosen (the first one was wrong)
    latin      Esc kept the Latin letters (git, PLSE)

The file stays on this computer (~/.local/share/ats-ai/history.tsv) and is
never committed. Nothing is written in password fields or while learning
is paused from the input menu.
"""

from pathlib import Path

HISTORY = Path.home() / ".local" / "share" / "ats-ai" / "history.tsv"


def record(context, latin, cyrillic, how, path=HISTORY):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{context}\t{latin.lower()}\t{cyrillic.lower()}\t{how}\n")
