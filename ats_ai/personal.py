"""Words the user corrected, used at once without any training.

Corrections come from the history file: a candidate picked (uur -> өөр) or
Latin kept with Esc (git -> git). "undone" rows cancel an earlier correction.

The same Latin can need different words: uu is уу or үү depending on the
word before it. So a correction made after the same previous word always
applies, but a correction from elsewhere applies only while the user has
never chosen anything else for that Latin. Otherwise the model decides.

Word lists hold spellings written by hand: abbreviations and the user's own
data/my_words.tsv. They reload when the file changes, so an edit works on the
next key press. A bad line is skipped; it must never break typing.
"""

import logging

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


class Personal:
    def __init__(self, path=HISTORY):
        self.picks = {}     # latin -> [(previous word, cyrillic), ...], oldest first
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            row = line.split("\t")
            if len(row) != 4:
                continue
            context, latin, cyrillic, how = row
            if how in ("picked", "latin"):
                self.learn(context, latin, cyrillic)
            elif how == "undone":
                self.forget(context, latin, cyrillic)

    def learn(self, context, latin, cyrillic):
        self.picks.setdefault(latin, []).append((previous_word(context), cyrillic))

    def forget(self, context, latin, cyrillic):
        pick = (previous_word(context), cyrillic)
        picks = self.picks.get(latin, [])
        if pick in picks:
            # Remove the newest copy; older ones are separate corrections.
            del picks[len(picks) - 1 - picks[::-1].index(pick)]

    def best(self, context, latin):
        """The word to offer first for this Latin, or None to trust the model."""
        picks = self.picks.get(latin, [])
        previous = previous_word(context)
        for word, cyrillic in reversed(picks):
            if word == previous:
                return cyrillic
        if len({cyrillic for _, cyrillic in picks}) == 1:
            return picks[-1][1]
        return None
