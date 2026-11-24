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


def model_file(name, folder=MODELS):
    """models/<name> as a file to load: the numpy .npz if there is one, else the torch .pt."""
    stem = Path(name).stem
    for suffix in (".npz", ".pt"):
        if (folder / (stem + suffix)).exists():
            return folder / (stem + suffix)
    return folder / name


class Model:
    """The model named in settings.json; switched when the setting changes.

    Uses models/vN.npz with numpy (installed copies, no torch) when it exists,
    otherwise models/vN.pt with torch (the development machine).
    """

    def __init__(self, config, folder=MODELS):
        self.config = config
        self.folder = folder
        self.name = None
        self.run = None

    def __call__(self, context, latin):
        return self.current()(context, latin)

    def current(self):
        name = self.config.get("model")
        if name != self.name:
            try:
                run = self._load(model_file(name, self.folder))
                run("", "sain")  # the first call is slow; do it now
            except Exception as error:  # keep typing with the model we have
                logging.warning("model %s not loaded: %s", name, error)
                if self.run is not None:
                    return self.run
                newest = sorted(self.folder.glob("*.np[z]")) or sorted(self.folder.glob("*.pt"))
                run = self._load(newest[-1])
            self.name, self.run = name, run
            logging.info("model %s", name)
        return self.run

    @staticmethod
    def _load(path):
        if path.suffix == ".npz":
            from ats_ai.numpy_model import NumpyModel

            return NumpyModel(path)
        from ats_ai.model import candidates, load  # torch only here

        net, vocab = load(path, "cpu")
        return lambda context, latin: candidates(net, vocab, context, latin)


class Typing:
    def __init__(self, convert=None, config=None, personal=None, root=ROOT, history=HISTORY):
        self.history = history
        self.config = config or Config(history.parent / "settings.json")
        self.convert = convert or Model(self.config)
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
