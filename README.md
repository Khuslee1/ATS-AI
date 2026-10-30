# ATS-AI

Mongolian typed in Latin letters becomes Cyrillic, like
[ATS](https://github.com/Khuslee1/ATS), but a small model trained on
chat-style typing does the conversion instead of hand-written rules.
On real chat messages it gets 82% of words right (ATS: 66%).

## Install the input method (Ubuntu, GNOME)

Needs a trained model at `models/base.pt` (see Training) and `.venv`.

```bash
sudo apt install python3-gi gir1.2-ibus-1.0
sudo cp engine/ats-ai.xml /usr/share/ibus/component/ats-ai.xml
ibus write-cache
ibus restart
```

Then Settings → Keyboard → Input Sources → + → Mongolian → **ATS-AI**.
`engine/ats-ai.xml` points at `/home/khuslee/practice/ATS-AI`; edit the
`<exec>` path if the repo lives elsewhere. Errors go to
`~/.cache/ats-ai-engine.log`.

Keys are the same as in ATS: Space/punctuation confirms the word,
Up/Down or `1`–`9` picks a candidate, Enter only confirms, Esc keeps Latin.

Every word you keep is saved to `~/.local/share/ats-ai/history.tsv` so the
model can learn your spelling. Nothing is saved in password fields or while
"Суралцахыг түр зогсоох" is checked in the input menu.

## Training

```bash
python3 -m venv .venv
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu126   # GTX 10xx; pick the build for your GPU
python3 -I tools/make_pairs.py data/synthetic.tsv CORPUS...                       # ~10M rows, 2 min
.venv/bin/python tools/train.py data/synthetic.tsv models/base.pt --epochs 2      # ~4 h on a GTX 1060
.venv/bin/python -m ats_ai.evaluate models/base.pt tests/real_chat.tsv -v
```

The corpora (not in git, put them in `data/raw/`):

- Mongolian Wikipedia, CirrusSearch dump:
  https://dumps.wikimedia.org/other/cirrus_search_index/
  (`mnwiki_content-*.json.bz2`)
- Leipzig news 2020:
  https://downloads.wortschatz-leipzig.de/corpora/mon_news_2020_100K.tar.gz

Training saves its progress every 1000 steps; after a stop or power cut,
run the same command with `--resume`.

## Data files

| File | What |
|---|---|
| `data/abbreviations.tsv` | chat abbreviations (bn, bga, gvl) used by make_pairs.py |
| `data/chatgpt_pairs.tsv` | 166 chat sentences, validation set |
| `tests/real_chat.tsv` | 21 real typed messages, test only, never trained on |
| `tools/check_coverage.py` | which real words the training data teaches |
