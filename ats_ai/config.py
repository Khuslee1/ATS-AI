"""User settings shared by the input method and the settings app.

~/.local/share/ats-ai/settings.json, for example
    {"model": "v4.pt", "paused": false, "escapes": 2}

    model     file in models/ the input method converts with ("" = the newest)
    paused    true: nothing is saved to the history or learned
    escapes   how many times Esc must keep the same word in Latin before it
              is always kept (0 = never learn from Esc)
    tester    tester code used in export files (share.py)
    shared_upto  history line the next export starts from

The file is read again whenever it changes, so the app's changes reach the
input method on the next key press. A broken or missing file means the
defaults; it must never break typing.
"""

import json
import logging
from pathlib import Path

from ats_ai.history import HISTORY

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
PATH = HISTORY.parent / "settings.json"
DEFAULTS = {"model": "", "paused": False, "escapes": 2, "tester": "", "shared_upto": 0}
ESCAPE_CHOICES = (1, 2, 0)


class Config:
    def __init__(self, path=PATH):
        self.path = path
        self.mtime = None
        self.values = dict(DEFAULTS)

    def _reload(self):
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self.mtime, self.values = None, dict(DEFAULTS)
            return
        if mtime == self.mtime:
            return
        self.mtime = mtime
        values = dict(DEFAULTS)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                values.update({k: data[k] for k in DEFAULTS if k in data})
        except (OSError, UnicodeDecodeError, ValueError) as error:
            logging.warning("%s unreadable, using defaults: %s", self.path, error)
        if not isinstance(values["shared_upto"], int) or values["shared_upto"] < 0:
            values["shared_upto"] = 0
        if values["escapes"] not in ESCAPE_CHOICES:
            values["escapes"] = DEFAULTS["escapes"]
        self.values = values

    def get(self, key):
        self._reload()
        return self.values[key]

    def save(self, **changes):
        self._reload()
        values = {**self.values, **{k: v for k, v in changes.items() if k in DEFAULTS}}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)  # never half-written for the input method
        self._reload()


def models(folder=MODELS):
    """Model files to choose from, newest first, one per version.

    v5.npz (numpy, what installed copies have) is listed instead of v5.pt
    (torch) when both exist; checkpoints *.pt.last are skipped.
    """
    files = {}
    for p in sorted(folder.glob("*.pt")) + sorted(folder.glob("*.npz")):
        if p.is_file():
            files[p.stem] = p  # .npz after .pt: it wins
    return sorted(files.values(), key=lambda p: p.stat().st_mtime, reverse=True)
