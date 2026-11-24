"""What happens to one typed word, without any input-method framework.

The IBus engine (Linux) and the ATS-AI server (Windows, behind PIME) both use
this, so the two behave the same:
    options(context, latin)          candidates for the word being typed
    commit(context, latin, word, how) the word was sent: save and learn
    undo(context, latin, word, how)   Backspace right after it: take it back

context is the last committed Cyrillic words (lowercase, space-separated),
latin the letters as typed (case kept, for Sain -> Сайн).
how is accepted / picked / latin, see history.py.

The model is loaded lazily by a `convert` function (context, latin) ->
[(text, probability), ...] so tests can pass a fake one without torch.
"""

import logging
from pathlib import Path

from ats_ai.config import MODELS, Config
from ats_ai.history import HISTORY, record
from ats_ai.personal import Personal, WordList

ROOT = Path(__file__).resolve().parent.parent

# A candidate this close to the best one is worth showing: дуу 0.60 / дүү 0.26.
AMBIGUOUS_RATIO = 10


def match_case(src, out):
    """Keep the capitalisation of the Latin input: Sain -> Сайн, TSAI -> ЦАЙ."""
    if not out:
        return out
    if src.isupper() and len(src) > 1:
        return out.upper()
    if src[0].isupper():
        return out[0].upper() + out[1:]
    return out


class TorchModel:
    """The model named in settings.json; switched when the setting changes."""

    def __init__(self, config):
        self.config = config
        self.name = None
        self.net = self.vocab = None

    def __call__(self, context, latin):
        from ats_ai.model import candidates  # torch only when really used

        net, vocab = self.current()
        return candidates(net, vocab, context, latin)

    def current(self):
        from ats_ai.model import candidates, load

        name = self.config.get("model")
        if name != self.name:
            try:
                net, vocab = load(MODELS / name, "cpu")
                candidates(net, vocab, "", "sain")  # the first call is slow; do it now
            except Exception as error:  # keep typing with the model we have
                logging.warning("model %s not loaded: %s", name, error)
                if self.net is not None:
                    return self.net, self.vocab
                net, vocab = load(MODELS / "v2.pt", "cpu")
            self.name, self.net, self.vocab = name, net, vocab
            logging.info("model %s", name)
        return self.net, self.vocab


class Typing:
    def __init__(self, convert=None, config=None, personal=None, root=ROOT, history=HISTORY):
        self.history = history
        self.config = config or Config(history.parent / "settings.json")
        self.convert = convert or TorchModel(self.config)
        self.personal = personal or Personal(history, config=self.config)
        self.my_words = WordList(root / "data" / "my_words.tsv")
        self.abbreviations = WordList(root / "data" / "abbreviations.tsv")

    @property
    def paused(self):
        return self.config.get("paused")

    def options(self, context, latin):
        """Candidates, best first, in the case the user typed."""
        if not latin:
            return []
        lower = latin.lower()
        found = self.convert(context, lower)
        best = found[0][1] if found else 0
        model = [text for text, p in found if p * AMBIGUOUS_RATIO >= best]
        # The user's own list is final. Otherwise corrections, then known
        # abbreviations go first; the model's words stay in the list so a
        # wrong one can be changed back.
        options = self.my_words.get(lower) or list(dict.fromkeys([
            *filter(None, [self.personal.best(context, lower)]),
            *self.abbreviations.get(lower),
            *model,
        ]))
        return [match_case(latin, o) for o in options] or [latin]

    def commit(self, context, latin, word, how):
        if self.paused:
            return
        latin, word = latin.lower(), word.lower()
        record(context, latin, word, how, self.history)
        if how in ("picked", "latin"):
            self.personal.learn(context, latin, word, how)

    def undo(self, context, latin, word, how):
        if self.paused:
            return
        latin, word = latin.lower(), word.lower()
        record(context, latin, word, "undone", self.history)
        if how in ("picked", "latin"):
            self.personal.forget(context, latin, word, how)
