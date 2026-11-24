"""The model without torch: the same transformer written in numpy.

What users install. tools/export_weights.py turns models/vN.pt into
models/vN.npz (the weights as numpy arrays + the characters); this file runs
them with the same beam search as model.candidates:

    NumpyModel("models/v5.npz")(context, latin) -> [(text, probability), ...]

The maths matches torch's nn.Transformer as used in model.Converter: post-norm
layers, ReLU, 4 heads, encoder and decoder each followed by a LayerNorm.
numpy is ~20 MB; torch would be ~250 MB.
"""

import math
import os

# The matrices are small: many BLAS threads cost more than they save
# (45 ms instead of 70 ms a word). Only works before numpy is first imported.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import numpy as np  # noqa: E402

from ats_ai.vocab import BOS, EOS, PAD, Vocab  # noqa: E402

BEAMS = 3
EPS = 1e-5


def layer_norm(x, w, b):
    mean = x.mean(-1, keepdims=True)
    var = x.var(-1, keepdims=True)
    return (x - mean) / np.sqrt(var + EPS) * w + b


def softmax(x):
    x = x - x.max(-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(-1, keepdims=True)


class NumpyModel:
    def __init__(self, path):
        data = np.load(path, allow_pickle=False)
        self.w = {k: data[k] for k in data.files if k not in ("chars", "config")}
        self.vocab = Vocab(str(data["chars"]))
        config = dict(zip(*[iter(data["config"].tolist())] * 2))
        self.dim, self.heads, self.layers = int(config["dim"]), int(config["heads"]), int(config["layers"])
        self.max_out = int(config["max_out"])

    # --- the network ---------------------------------------------------------

    def embed(self, ids):
        w = self.w
        return w["embed.weight"][ids] * math.sqrt(self.dim) + w["position.weight"][np.arange(ids.shape[1])]

    def attention(self, prefix, q_in, kv_in, mask):
        """nn.MultiheadAttention (batch_first). mask: added to scores, broadcast to [n, h, q, k]."""
        w, d, h = self.w, self.dim, self.heads
        wq, wk, wv = np.split(w[prefix + "in_proj_weight"], 3)
        bq, bk, bv = np.split(w[prefix + "in_proj_bias"], 3)
        n, lq, lk = q_in.shape[0], q_in.shape[1], kv_in.shape[1]

        def heads(x, l):
            return x.reshape(n, l, h, d // h).transpose(0, 2, 1, 3)

        q = heads(q_in @ wq.T + bq, lq)
        k = heads(kv_in @ wk.T + bk, lk)
        v = heads(kv_in @ wv.T + bv, lk)
        scores = q @ k.transpose(0, 1, 3, 2) / math.sqrt(d // h) + mask
        out = (softmax(scores) @ v).transpose(0, 2, 1, 3).reshape(n, lq, d)
        return out @ w[prefix + "out_proj.weight"].T + w[prefix + "out_proj.bias"]

    def feed_forward(self, prefix, x):
        w = self.w
        hidden = np.maximum(x @ w[prefix + "linear1.weight"].T + w[prefix + "linear1.bias"], 0)
        return hidden @ w[prefix + "linear2.weight"].T + w[prefix + "linear2.bias"]

    def norm(self, prefix, x):
        return layer_norm(x, self.w[prefix + "weight"], self.w[prefix + "bias"])

    def encode(self, src):
        pad = np.where(src == PAD, -np.inf, 0.0).astype(np.float32)[:, None, None, :]
        x = self.embed(src)
        for i in range(self.layers):
            p = f"transformer.encoder.layers.{i}."
            x = self.norm(p + "norm1.", x + self.attention(p + "self_attn.", x, x, pad))
            x = self.norm(p + "norm2.", x + self.feed_forward(p, x))
        return self.norm("transformer.encoder.norm.", x)

    def project(self, prefix, x, which):
        """x @ (q | k | v weights) of one attention layer, split into heads [n, h, l, dh]."""
        w, d, h = self.w, self.dim, self.heads
        part = {"q": 0, "k": 1, "v": 2}[which]
        weight = w[prefix + "in_proj_weight"][part * d:(part + 1) * d]
        bias = w[prefix + "in_proj_bias"][part * d:(part + 1) * d]
        n, l = x.shape[0], x.shape[1]
        return (x @ weight.T + bias).reshape(n, l, h, d // h).transpose(0, 2, 1, 3)

    def attend(self, prefix, q, k, v, mask=0.0):
        n, h, lq, dh = q.shape
        scores = q @ k.transpose(0, 1, 3, 2) / math.sqrt(dh) + mask
        out = (softmax(scores) @ v).transpose(0, 2, 1, 3).reshape(n, lq, h * dh)
        return out @ self.w[prefix + "out_proj.weight"].T + self.w[prefix + "out_proj.bias"]

    def step(self, token, position, cache, cross, memory_pad):
        """One decoder step for the last token of each beam, with cached keys/values.

        token [n] ids, cache[i] = (k, v) of layer i's self-attention so far.
        Post-norm layers are causal, so earlier positions never change: their
        keys and values are kept instead of computing the whole word again.
        """
        w = self.w
        x = (w["embed.weight"][token] * math.sqrt(self.dim) + w["position.weight"][position])[:, None]
        for i in range(self.layers):
            p = f"transformer.decoder.layers.{i}."
            k = self.project(p + "self_attn.", x, "k")
            v = self.project(p + "self_attn.", x, "v")
            if cache[i] is not None:
                k = np.concatenate([cache[i][0], k], 2)
                v = np.concatenate([cache[i][1], v], 2)
            cache[i] = (k, v)
            q = self.project(p + "self_attn.", x, "q")
            x = self.norm(p + "norm1.", x + self.attend(p + "self_attn.", q, k, v))
            q = self.project(p + "multihead_attn.", x, "q")
            ck, cv = cross[i]
            x = self.norm(p + "norm2.", x + self.attend(p + "multihead_attn.", q, ck, cv, memory_pad))
            x = self.norm(p + "norm3.", x + self.feed_forward(p, x))
        x = self.norm("transformer.decoder.norm.", x[:, 0])
        logits = x @ w["out.weight"].T + w["out.bias"]
        top = logits.max(-1, keepdims=True)
        return logits - top - np.log(np.exp(logits - top).sum(-1, keepdims=True))

    # --- beam search (as model.candidates) ------------------------------------

    def __call__(self, context, latin, beams=BEAMS):
        """The `beams` most likely spellings of one word, as (text, probability)."""
        src = np.array([self.vocab.source(context, latin)], dtype=np.int64)
        memory = self.encode(src)
        memory_pad = np.where(src == PAD, -np.inf, 0.0).astype(np.float32)[:, None, None, :]
        # The source side of cross-attention is the same for every step: once.
        cross = [(self.project(f"transformer.decoder.layers.{i}.multihead_attn.", memory, "k"),
                  self.project(f"transformer.decoder.layers.{i}.multihead_attn.", memory, "v"))
                 for i in range(self.layers)]
        alive = [([BOS], 0.0)]           # (ids so far, log probability)
        cache = [None] * self.layers     # per layer (k, v) for the alive beams, in order
        finished = []
        for position in range(self.max_out + 1):
            n = len(alive)
            last = np.array([ids[-1] for ids, _ in alive], dtype=np.int64)
            log_probs = self.step(last, position, cache,
                                  [(np.repeat(k, n, 0), np.repeat(v, n, 0)) for k, v in cross], memory_pad)
            options = []
            for b, ((ids, score), row) in enumerate(zip(alive, log_probs)):
                for i in np.argsort(-row)[:beams]:
                    options.append((ids + [int(i)], score + float(row[i]), b))
            options.sort(key=lambda o: o[1], reverse=True)
            alive, parents = [], []
            for ids, score, b in options:
                if ids[-1] == EOS:
                    finished.append((ids, score))
                elif len(alive) < beams:
                    alive.append((ids, score))
                    parents.append(b)
            # Each surviving beam keeps its parent's cached keys and values.
            cache = [(k[parents], v[parents]) for k, v in cache] if parents else cache
            finished = sorted(finished, key=lambda o: o[1], reverse=True)[:beams]
            # Scores only fall, so stop once no unfinished word can still make the list.
            if not alive or (len(finished) == beams and alive[0][1] <= finished[-1][1]):
                break
        seen, out = set(), []
        for ids, score in finished:
            text = self.vocab.decode(ids[1:])
            if text and text not in seen:
                seen.add(text)
                out.append((text, math.exp(score)))
        return out or [(latin, 1.0)]
