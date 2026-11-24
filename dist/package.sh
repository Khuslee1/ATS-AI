#!/usr/bin/env bash
# Build the tester package: dist/out/ats-ai-linux-<date>.tar.gz
#   dist/package.sh            (uses the model chosen in settings, else the newest)
#   MODEL=v5.pt dist/package.sh
# Only the program and one model go in — never your history, labels or my_words.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${MODEL:-$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.local/share/ats-ai/settings.json"))).get("model",""))' 2>/dev/null || true)}"
[ -n "$MODEL" ] && [ -f "$REPO/models/$MODEL" ] || MODEL="$(basename "$(ls -t "$REPO"/models/*.pt | head -1)")"

OUT="$REPO/dist/out"
WORK="$(mktemp -d)"
PKG="$WORK/ats-ai"
mkdir -p "$PKG"/{ats_ai,engine,app,models,data,dist} "$OUT"

cp "$REPO"/ats_ai/*.py "$PKG/ats_ai/"
cp "$REPO/engine/main.py" "$PKG/engine/"
cp "$REPO/app/settings.py" "$REPO/app/icon.png" "$PKG/app/"
# The numpy weights (no torch for users); made by tools/export_weights.py.
NPZ="$REPO/models/${MODEL%.*}.npz"
[ -f "$NPZ" ] || { echo "No $NPZ — run: .venv/bin/python tools/export_weights.py models/$MODEL"; exit 1; }
cp "$NPZ" "$PKG/models/"
cp "$REPO/data/abbreviations.tsv" "$PKG/data/"
printf '# Your own words, used before the model. One per line: latin<TAB>cyrillic\n' > "$PKG/data/my_words.tsv"
cp "$REPO"/dist/{ats-ai.xml.in,ats-ai-settings.desktop.in} "$PKG/dist/"
cp "$REPO"/dist/{install.sh,uninstall.sh,README-mn.txt} "$PKG/"
chmod +x "$PKG"/*.sh

NAME="ats-ai-linux-$(date +%Y-%m-%d).tar.gz"
tar -czf "$OUT/$NAME" -C "$WORK" ats-ai
rm -rf "$WORK"
echo "$OUT/$NAME  (model $MODEL, $(du -h "$OUT/$NAME" | cut -f1))"
