import math

import torch

from ats_ai.model import CHARS, EOS, candidates, Vocab


class ScriptedModel:
    """Spells one word with high probability, with unlikely stops along the way."""

    def __init__(self, vocab, word):
        self.vocab = vocab
        self.word = vocab.encode(word)

    def encode(self, src):
        return torch.zeros(1, src.shape[1], 1)

    def decode(self, ys, memory, src):
        logits = torch.full((len(ys), ys.shape[1], len(self.vocab)), -30.0)
        for row, ids in enumerate(ys.tolist()):
            spelled = ids[1:]
            if spelled == self.word[:len(spelled)] and len(spelled) < len(self.word):
                logits[row, -1, self.word[len(spelled)]] = math.log(0.9)
                logits[row, -1, EOS] = math.log(0.01)
            else:
                logits[row, -1, EOS] = 0.0
        return logits


def test_beam_search_does_not_stop_before_the_likely_long_word():
    vocab = Vocab(CHARS)
    found = candidates(ScriptedModel(vocab, "ажиллахгүй"), vocab, "", "ajillahgui")
    assert found[0][0] == "ажиллахгүй"


def test_latin_words_are_left_out_of_the_context():
    vocab = Vocab(CHARS)
    assert vocab.source("github", "ruu") == vocab.source("", "ruu")
    assert vocab.source("миний google-ээс", "ruu") == vocab.source("миний", "ruu")


def test_cyrillic_context_is_kept():
    vocab = Vocab(CHARS)
    assert vocab.source("миний 2", "ruu") == vocab.encode("миний 2") + [3] + vocab.encode("ruu")
