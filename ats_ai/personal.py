"""Words the user corrected, used at once without any training.

Corrections come from the history file: a candidate picked (uur -> өөр) or
Latin kept with Esc (git -> git). "undone" rows cancel an earlier correction.

The same Latin can need different words: uu is уу or үү depending on the
word before it. So a correction made after the same previous word always
applies, but a correction from elsewhere applies only while the user has
never chosen anything else for that Latin. Otherwise the model decides.

Word lists hold spellings written by hand: abbreviations and the user's own
~/.local/share/ats-ai/my_words.tsv. They reload when the file changes, so an edit works on the
next key press. A bad line is skipped; it must never break typing.

Corrections the user removed in the settings app are listed in forgotten.tsv
(latin<TAB>cyrillic, see ats_ai/words.py) and are not used. Picking the same
word again later takes it off that list.
"""

import logging

from ats_ai.config import Config
from ats_ai.history import HISTORY


def previous_word(context):
    words = context.split()
    return words[-1] if words else ""


class WordList:
    """latin<TAB>cyrillic lines; one Latin may have several lines."""

    def __init__(self, path):
        self.path = path
        self.mtime = None
        self.words = {}

    def get(self, latin):
        self._reload()
        return self.words.get(latin, [])

    def _reload(self):
        try:
            mtime = self.path.stat().st_mtime
            if mtime == self.mtime:
                return
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self.words = {}
            self.mtime = None
            return
        self.mtime = mtime
        self.words = {}
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            row = [part.strip() for part in line.split("\t")]
            if len(row) != 2 or not all(row):
                logging.warning("%s line %d skipped: needs latin<TAB>cyrillic", self.path, number)
                continue
            self.words.setdefault(row[0].lower(), []).append(row[1])


class Labels:
    """labels.tsv from the settings app: words the user marked right or wrong.

    line<TAB>context<TAB>latin<TAB>output<TAB>verdict<TAB>correct
    line is the history line number (the history only grows, so it stays put);
    verdict is "ok" or "wrong", and a wrong one has the correct word. The last
    row for a line wins. Reloads when the file changes.
    """

    def __init__(self, path):
        self.path = path
        self.mtime = None
        self.rows = {}

    def all(self):
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self.rows, self.mtime = {}, None
            return self.rows
        if mtime != self.mtime:
            self.mtime = mtime
            self.rows = {}
            try:
                text = self.path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = ""
            for line in text.splitlines():
                row = line.split("\t")
                if len(row) == 6 and row[0].isdigit() and row[4] in ("ok", "wrong"):
                    self.rows[int(row[0])] = row[1:]
        return self.rows

    def fixes(self, latin):
        """(previous word, correct word) of the wrong ones for this Latin."""
        return [
            (previous_word(context), correct)
            for context, lat, _, verdict, correct in self.all().values()
            if lat == latin and verdict == "wrong" and correct
        ]


# Esc keeps the Latin letters. Once is often just escaping a bad guess
# (thdee -> түүхдээ); keeping the same word twice means "always Latin" (git).
# How many times is the user's choice ("escapes" in settings.json, 0 = never).


class Personal:
    def __init__(self, path=HISTORY, forgotten_path=None, config=None):
        self.config = config or Config(path.parent / "settings.json")
        self.picks = {}     # latin -> [(previous word, cyrillic), ...], oldest first
        self.escapes = {}   # latin -> times kept Latin with Esc, minus undone
        self.fresh = {}     # latin -> Esc since it was forgotten (this run only)
        self.forgotten = WordList(forgotten_path or path.parent / "forgotten.tsv")
        self.labels = Labels(path.parent / "labels.tsv")
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            row = line.split("\t")
            if len(row) != 4:
                continue
            context, latin, cyrillic, how = row
            if how == "picked":
                self._add(context, latin, cyrillic)  # old rows: never unforget
            elif how == "latin":
                if self._enough(self._escape(latin, 1)):
                    self._add(context, latin, cyrillic)
            elif how == "undone":
                # Undone rows do not say how the word was kept; a word kept
                # with Esc is its own Latin.
                self.forget(context, latin, cyrillic, "latin" if cyrillic == latin else "picked")

    def _add(self, context, latin, cyrillic):
        self.picks.setdefault(latin, []).append((previous_word(context), cyrillic))

    def _enough(self, escapes):
        needed = self.config.get("escapes")
        return needed > 0 and escapes >= needed

    def _escape(self, latin, step):
        self.escapes[latin] = max(0, self.escapes.get(latin, 0) + step)
        return self.escapes[latin]

    def learn(self, context, latin, cyrillic, how="picked"):
        """A correction made just now while typing: "picked" or "latin" (Esc)."""
        forgotten = cyrillic in self.forgotten.get(latin)
        if how == "latin":
            if not self._enough(self._escape(latin, 1)):
                return
            if forgotten:
                # Forgotten in the settings app: needs two new Esc again.
                self.fresh[latin] = self.fresh.get(latin, 0) + 1
                if not self._enough(self.fresh[latin]):
                    return
        self._add(context, latin, cyrillic)
        if forgotten:
            self._unforget(latin, cyrillic)
            self.fresh.pop(latin, None)

    def _unforget(self, latin, cyrillic):
        """Chosen again after being forgotten: use it again."""
        path = self.forgotten.path
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            keep = [l for l in lines if l.rstrip("\n").split("\t") != [latin, cyrillic]]
            path.write_text("".join(keep), encoding="utf-8")
        except OSError as error:
            logging.warning("could not update %s: %s", path, error)

    def forget(self, context, latin, cyrillic, how="picked"):
        """Backspace right after a word: take back what it taught."""
        if how == "latin":
            self._escape(latin, -1)
            if self.fresh.get(latin):
                self.fresh[latin] -= 1
        pick = (previous_word(context), cyrillic)
        picks = self.picks.get(latin, [])
        if pick in picks:
            # Remove the newest copy; older ones are separate corrections.
            del picks[len(picks) - 1 - picks[::-1].index(pick)]

    def best(self, context, latin):
        """The word to offer first for this Latin, or None to trust the model."""
        dropped = self.forgotten.get(latin)
        # Words fixed in the settings app count as the newest corrections.
        picks = [p for p in self.picks.get(latin, []) + self.labels.fixes(latin) if p[1] not in dropped]
        previous = previous_word(context)
        for word, cyrillic in reversed(picks):
            if word == previous:
                return cyrillic
        if len({cyrillic for _, cyrillic in picks}) == 1:
            return picks[-1][1]
        return None
