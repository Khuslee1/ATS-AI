# ATS-AI

Mongolian typed in Latin letters becomes Cyrillic, like
[ATS](https://github.com/Khuslee1/ATS), but a small model trained on
chat-style typing does the conversion instead of hand-written rules.
On real chat messages it gets 92% of words right (ATS: 66%).

## Install the input method (Ubuntu, GNOME)

Needs a trained model at `models/v2.pt` (see Training) and `.venv`.

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

## Your own words

`data/my_words.tsv` holds spellings the model should never guess, one
`latin<TAB>cyrillic` per line (`bnu` → `байна уу`, `ats` → `ATS`). Edits work
on the next key press, no restart. The file is private and not in git.
Without an entry, a candidate you pick or Latin you keep with Esc is
remembered too. Backspace right after a word cancels what it taught.

## Training

```bash
python3 -m venv .venv
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cu126   # GTX 10xx; pick the build for your GPU
python3 -I tools/make_pairs.py data/synthetic.tsv CORPUS...                       # ~10M rows, 2 min
.venv/bin/python tools/train.py data/synthetic.tsv models/v2.pt --epochs 2      # ~4 h on a GTX 1060
.venv/bin/python -m ats_ai.evaluate models/v2.pt tests/real_chat.tsv -v
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
| `data/chatgpt_pairs.tsv` | 166 chat sentences, added to training |
| `data/foreign.tsv` | foreign words to keep in Latin or spell the Mongolian way |
| `tests/real_chat.tsv` | 21 real typed messages, picks the best checkpoint, never trained on |
| `tests/history_chat.tsv` | real typed lines from the history, final test, never trained on, not in git |
| `tools/check_coverage.py` | which real words the training data teaches |
