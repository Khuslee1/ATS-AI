"""A small character-level transformer that converts one typed Latin word.

Input:  the previous Cyrillic words (context) and the Latin word being typed,
        as characters: "мэдэж байгааг|nariivchlan"
Output: the Cyrillic for that word, possibly several words: bolu -> "болов уу".

The context lets the model pick дуу or дүү from what came before.
"""

import math

import torch
from torch import nn

from ats_ai.vocab import (  # noqa: F401  (re-exported for older imports)
    BOS, CHARS, CONTEXT_WORDS, EOS, LATIN, MAX_IN, MAX_OUT, PAD, SEP, Vocab,
)


class Converter(nn.Module):
    def __init__(self, vocab_size, dim=256, heads=4, layers=3, ff=1024, dropout=0.1):
        super().__init__()
        self.dim = dim
        self.embed = nn.Embedding(vocab_size, dim, padding_idx=PAD)
        self.position = nn.Embedding(max(MAX_IN, MAX_OUT + 2), dim)
        self.transformer = nn.Transformer(
            dim, heads, layers, layers, ff, dropout, batch_first=True
        )
        self.out = nn.Linear(dim, vocab_size)

    def _embed(self, ids):
        positions = torch.arange(ids.size(1), device=ids.device)
        return self.embed(ids) * math.sqrt(self.dim) + self.position(positions)

    def encode(self, src):
        return self.transformer.encoder(
            self._embed(src), src_key_padding_mask=src == PAD
        )

    def decode(self, tgt, memory, src):
        mask = self.transformer.generate_square_subsequent_mask(
            tgt.size(1), device=tgt.device
        )
        hidden = self.transformer.decoder(
            self._embed(tgt),
            memory,
            tgt_mask=mask,
            tgt_is_causal=True,
            tgt_key_padding_mask=tgt == PAD,
            memory_key_padding_mask=src == PAD,
        )
        return self.out(hidden)

    def forward(self, src, tgt):
        return self.decode(tgt, self.encode(src), src)


def pad(rows, length=None):
    length = length or max(len(r) for r in rows)
    out = torch.full((len(rows), length), PAD, dtype=torch.long)
    for i, r in enumerate(rows):
        out[i, :len(r)] = torch.tensor(r[:length])
    return out


@torch.no_grad()
def translate(model, vocab, sources, device):
    """Greedy decoding for a batch of encoder inputs (lists of ids)."""
    src = pad(sources).to(device)
    memory = model.encode(src)
    ys = torch.full((len(sources), 1), BOS, dtype=torch.long, device=device)
    done = torch.zeros(len(sources), dtype=torch.bool, device=device)
    for _ in range(MAX_OUT + 1):
        next_id = model.decode(ys, memory, src)[:, -1].argmax(-1)
        next_id[done] = PAD
        ys = torch.cat([ys, next_id[:, None]], dim=1)
        done |= next_id == EOS
        if done.all():
            break
    return [vocab.decode(row[1:].tolist()) for row in ys]


@torch.no_grad()
def candidates(model, vocab, context, latin, device="cpu", beams=3):
    """The `beams` most likely spellings of one word, as (text, probability)."""
    src = pad([vocab.source(context, latin)]).to(device)
    memory = model.encode(src)
    alive = [([BOS], 0.0)]           # (ids so far, log probability)
    finished = []
    for _ in range(MAX_OUT + 1):
        ys = torch.tensor([ids for ids, _ in alive], device=device)
        n = len(alive)
        log_probs = model.decode(ys, memory.expand(n, -1, -1), src.expand(n, -1))[:, -1]
        log_probs = log_probs.log_softmax(-1)
        options = []
        for (ids, score), row in zip(alive, log_probs):
            top = row.topk(beams)
            for lp, i in zip(top.values.tolist(), top.indices.tolist()):
                options.append((ids + [i], score + lp))
        options.sort(key=lambda o: o[1], reverse=True)
        alive = []
        for ids, score in options:
            if ids[-1] == EOS:
                finished.append((ids, score))
            elif len(alive) < beams:
                alive.append((ids, score))
        finished = sorted(finished, key=lambda o: o[1], reverse=True)[:beams]
        # Scores only fall, so stop once no unfinished word can still make the
        # list. Stopping at the first three finished keeps short unlikely ones.
        if not alive or (len(finished) == beams and alive[0][1] <= finished[-1][1]):
            break
    seen, out = set(), []
    for ids, score in finished:
        text = vocab.decode(ids[1:])
        if text and text not in seen:
            seen.add(text)
            out.append((text, math.exp(score)))
    return out or [(latin, 1.0)]


def convert_sentences(model, vocab, sentences, device):
    """Convert whole Latin sentences word by word, feeding back own output."""
    words = [s.lower().split() for s in sentences]
    outputs = [[] for _ in sentences]
    for j in range(max((len(w) for w in words), default=0)):
        batch, sources = [], []
        for i, w in enumerate(words):
            if j >= len(w):
                continue
            if not w[j].isalpha():
                # Numbers and the like stay as typed: 2, 1r.
                outputs[i].append(w[j])
                continue
            context = " ".join(" ".join(outputs[i]).split()[-CONTEXT_WORDS:])
            batch.append(i)
            sources.append(vocab.source(context, w[j]))
        if sources:
            for i, text in zip(batch, translate(model, vocab, sources, device)):
                outputs[i].append(text)
    return [" ".join(o) for o in outputs]


def load(path, device):
    checkpoint = torch.load(path, map_location=device)
    vocab = Vocab(checkpoint["chars"])
    model = Converter(len(vocab), **checkpoint["config"]).to(device)
    model.load_state_dict(checkpoint["model"])
    model.eval()
    return model, vocab
