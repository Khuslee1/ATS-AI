"""Characters <-> token ids for the model. No torch: the installed input
method uses this with onnxruntime (onnx_model.py), training with torch (model.py).
"""

import re

PAD, BOS, EOS, SEP = 0, 1, 2, 3
CHARS = "abcdefghijklmnopqrstuvwxyz0123456789 -абвгдеёжзийклмноөпрстуүфхцчшщъыьэюя"
MAX_IN = 48
MAX_OUT = 32
CONTEXT_WORDS = 2
LATIN = re.compile("[a-z]")


class Vocab:
    def __init__(self, chars=CHARS):
        self.chars = chars
        self.index = {c: i + 4 for i, c in enumerate(chars)}

    def __len__(self):
        return len(self.chars) + 4

    def encode(self, text):
        return [self.index[c] for c in text if c in self.index]

    def source(self, context, latin):
        """Token ids for the encoder; context is cut from the left if too long."""
        # Training context is Cyrillic. After a Latin word the model garbles
        # the next words: gmail ruu -> gmail магилруу.
        context = " ".join(w for w in context.split() if not LATIN.search(w))
        word = self.encode(latin)[:MAX_IN - 1]
        room = MAX_IN - 1 - len(word)
        before = self.encode(context)[-room:] if room else []
        return before + [SEP] + word

    def target(self, cyrillic):
        return [BOS] + self.encode(cyrillic)[:MAX_OUT] + [EOS]

    def decode(self, ids):
        out = []
        for i in ids:
            if i == EOS:
                break
            if i >= 4:
                out.append(self.chars[i - 4])
        return "".join(out)
