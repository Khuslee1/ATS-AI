"""Turn a trained model (.pt, torch) into .npz for numpy_model.py (no torch).

    .venv/bin/python tools/export_weights.py models/v5.pt     -> models/v5.npz

Then checks numpy against torch on a set of words; exits 1 if they differ.
Run it after every training: the installed input method uses the .npz.
"""

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ats_ai.model import MAX_OUT, candidates, load  # noqa: E402
from ats_ai.numpy_model import NumpyModel  # noqa: E402

CHECK = [("", "sain"), ("", "harij"), ("миний", "duu"), ("энэ", "duu"), ("тийм", "bgaldaa"),
         ("", "surguuli"), ("", "bn"), ("", "computer"), ("би", "ochij"), ("", "x"),
         ("маш", "ih"), ("", "uuruu"), ("за", "tegyee"), ("", "tsag")]


def main(path):
    checkpoint = torch.load(path, map_location="cpu")
    model, vocab = load(path, "cpu")
    out = Path(path).with_suffix(".npz")
    config = {**checkpoint["config"], "max_out": MAX_OUT}
    np.savez(
        out,
        chars=np.array(vocab.chars),
        config=np.array([str(x) for kv in config.items() for x in kv]),
        **{k: v.float().numpy() for k, v in model.state_dict().items()},
    )

    fast = NumpyModel(out)
    bad = 0
    with torch.no_grad():
        for context, latin in CHECK:
            a = candidates(model, vocab, context, latin)
            b = fast(context, latin)
            same = [t for t, _ in a] == [t for t, _ in b] and all(
                abs(p - q) < 1e-3 for (_, p), (_, q) in zip(a, b))
            bad += not same
            print(f"{'ok  ' if same else 'DIFF'} {latin:9} torch {[t for t, _ in a]}  numpy {[t for t, _ in b]}")
    print(f"{out}  {out.stat().st_size / 1e6:.1f} MB")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(sys.argv[1])
