"""Train the converter on rows from tools/make_pairs.py.

Usage:
    .venv/bin/python tools/train.py data/synthetic.tsv models/base.pt [--epochs 2] [--steps N]

Every epoch the model is scored on data/chatgpt_pairs.tsv (used to pick the
best checkpoint) and on tests/real_chat.tsv (reported only, never used to
choose). The best model goes to OUTPUT.

Progress is saved to OUTPUT.last every SAVE_EVERY steps and on Ctrl+C.
After a stop or a power cut, run the same command with --resume to carry
on from there. --steps N stops after N steps, for a quick speed check.
"""

import math
import os
import random
import sys
import time
from pathlib import Path

import torch
from torch import nn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ats_ai.evaluate import evaluate  # noqa: E402
from ats_ai.model import MAX_IN, MAX_OUT, PAD, Converter, Vocab, pad  # noqa: E402

CONFIG = {"dim": 256, "heads": 4, "layers": 3, "ff": 1024, "dropout": 0.1}
BATCH = 512
LEARNING_RATE = 5e-4
WARMUP_STEPS = 2000
LOG_EVERY = 500
SAVE_EVERY = 1000

VALIDATION = ROOT / "data" / "chatgpt_pairs.tsv"
TEST = ROOT / "tests" / "real_chat.tsv"


def load_rows(path, vocab):
    """Encode every row once into two padded int16 tensors (fits in RAM)."""
    sources, targets = [], []
    with open(path, encoding="utf-8") as f:
        for line in f:
            context, latin, cyrillic = line.rstrip("\n").split("\t")
            sources.append(vocab.source(context, latin))
            targets.append(vocab.target(cyrillic))
    print(f"{len(sources)} rows loaded", flush=True)
    return pad(sources, MAX_IN).short(), pad(targets, MAX_OUT + 2).short()


def trim(batch):
    """Cut the padding columns every row in the batch has."""
    used = (batch != PAD).any(0).nonzero().max().item() + 1
    return batch[:, :used].long()


def learning_rate(step, total):
    if step < WARMUP_STEPS:
        return LEARNING_RATE * step / WARMUP_STEPS
    progress = (step - WARMUP_STEPS) / max(1, total - WARMUP_STEPS)
    return LEARNING_RATE * 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))


def main(args):
    epochs, max_steps = 2, None
    resume = "--resume" in args
    if resume:
        args.remove("--resume")
    if "--epochs" in args:
        at = args.index("--epochs")
        epochs = int(args[at + 1])
        del args[at:at + 2]
    if "--steps" in args:
        at = args.index("--steps")
        max_steps = int(args[at + 1])
        del args[at:at + 2]
    data, output = args
    last = output + ".last"
    Path(output).parent.mkdir(parents=True, exist_ok=True)

    device = "cuda"
    torch.manual_seed(1)
    random.seed(1)
    vocab = Vocab()
    sources, targets = load_rows(data, vocab)

    model = Converter(len(vocab), **CONFIG).to(device)
    print(f"{sum(p.numel() for p in model.parameters()) / 1e6:.1f}M parameters", flush=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=0.01)
    loss_fn = nn.CrossEntropyLoss(ignore_index=PAD, label_smoothing=0.05)

    steps_per_epoch = len(sources) // BATCH
    total = max_steps or epochs * steps_per_epoch
    step, best = 0, -1.0

    if resume:
        state = torch.load(last, map_location=device)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        step, best = state["step"], state["best"]
        print(f"resuming at step {step}", flush=True)
    resumed_at = step
    started = time.time()

    def save(path, **extra):
        # Write to a temporary file first so a power cut mid-write
        # never leaves a broken checkpoint behind.
        state = {"model": model.state_dict(), "config": CONFIG, "chars": vocab.chars}
        state.update(extra)
        torch.save(state, path + ".tmp")
        os.replace(path + ".tmp", path)

    def save_progress():
        save(last, optimizer=optimizer.state_dict(), step=step, best=best)

    def check(epoch):
        nonlocal best
        model.eval()
        val, val_text = evaluate(model, vocab, VALIDATION, device)
        _, test_text = evaluate(model, vocab, TEST, device)
        model.train()
        print(f"epoch {epoch}: chatgpt_pairs {val_text} | real_chat {test_text}", flush=True)
        if val > best:
            best = val
            save(output)
            print(f"saved {output}", flush=True)
        save_progress()

    try:
        while step < total:
            epoch, first_batch = divmod(step, steps_per_epoch)
            # The order depends only on the epoch, so a resumed run
            # continues with exactly the batches it had not seen yet.
            order = torch.randperm(len(sources), generator=torch.Generator().manual_seed(epoch))
            model.train()
            for b in range(first_batch, steps_per_epoch):
                rows = order[b * BATCH:(b + 1) * BATCH]
                src = trim(sources[rows]).to(device)
                tgt = trim(targets[rows]).to(device)

                for group in optimizer.param_groups:
                    group["lr"] = learning_rate(step, total)
                logits = model(src, tgt[:, :-1])
                loss = loss_fn(logits.reshape(-1, logits.size(-1)), tgt[:, 1:].reshape(-1))
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                step += 1

                if step % LOG_EVERY == 0 or step == total:
                    rate = (step - resumed_at) / (time.time() - started)
                    left = (total - step) / rate / 60
                    print(f"step {step}/{total} loss {loss.item():.3f} "
                          f"{rate:.1f} steps/s, {left:.0f} min left", flush=True)
                if step % SAVE_EVERY == 0:
                    save_progress()
                if step == total:
                    break
            check(epoch + 1)
    except KeyboardInterrupt:
        save_progress()
        print(f"stopped at step {step}; continue later with --resume", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
