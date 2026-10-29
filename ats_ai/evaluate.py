"""Score a model on latin<TAB>cyrillic sentence files.

Usage:
    .venv/bin/python -m ats_ai.evaluate models/base.pt tests/real_chat.tsv [-v]

-v prints every sentence the model got wrong.
"""

import difflib
import sys

import torch

from ats_ai.model import convert_sentences, load


def read_pairs(path):
    pairs = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("#") or not line.strip():
            continue
        latin, cyrillic = line.rstrip("\n").split("\t")
        pairs.append((latin, cyrillic))
    return pairs


def score(outputs, golds):
    """(right words, total words, right sentences), words matched in order."""
    right = sentences = total = 0
    for out, gold in zip(outputs, golds):
        o, g = out.split(), gold.split()
        matcher = difflib.SequenceMatcher(a=g, b=o, autojunk=False)
        right += sum(block.size for block in matcher.get_matching_blocks())
        total += len(g)
        sentences += out == gold
    return right, total, sentences


def evaluate(model, vocab, path, device, verbose=False):
    pairs = read_pairs(path)
    outputs = convert_sentences(model, vocab, [l for l, _ in pairs], device)
    golds = [c for _, c in pairs]
    if verbose:
        for (latin, gold), out in zip(pairs, outputs):
            if out != gold:
                print(f"  {latin}\n    got  {out}\n    want {gold}")
    right, total, sentences = score(outputs, golds)
    return right / total, f"words {right}/{total} = {right / total:.0%}, sentences {sentences}/{len(pairs)}"


def main(args):
    verbose = "-v" in args
    args = [a for a in args if a != "-v"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, vocab = load(args[0], device)
    for path in args[1:]:
        print(f"{path}: {evaluate(model, vocab, path, device, verbose)[1]}")


if __name__ == "__main__":
    main(sys.argv[1:])
