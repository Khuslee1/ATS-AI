#!/usr/bin/env bash
# ATS-AI суулгагч (Ubuntu, GNOME, IBus).
#   tar xzf ats-ai-linux-*.tar.gz && cd ats-ai && ./install.sh
# Програмыг ~/.local/opt/ats-ai-д, таны үгс, түүхийг ~/.local/share/ats-ai-д хадгална.
# Интернет хэрэгтэй (Python сан ~100 MB татна). sudo нууц үгийг 1–2 удаа асууна.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/opt/ats-ai"
COMPONENT=/usr/share/ibus/component/ats-ai.xml

say() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

say "1/5 Шаардлагатай системийн багцууд"
sudo apt-get install -y python3-venv python3-gi gir1.2-ibus-1.0 ibus

say "2/5 Програмыг хуулж байна: $DEST"
mkdir -p "$DEST"
rm -rf "$DEST"/ats_ai "$DEST"/engine "$DEST"/app "$DEST"/models   # хуучин хувилбар
cp -r "$SRC"/ats_ai "$SRC"/engine "$SRC"/app "$SRC"/models "$DEST"/
mkdir -p "$DEST/data"
cp "$SRC/data/abbreviations.tsv" "$DEST/data/"
[ -f "$DEST/data/my_words.tsv" ] || cp "$SRC/data/my_words.tsv" "$DEST/data/"   # таны үгсийг дарахгүй

say "3/5 Python сангууд (хэдэн минут)"
python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install -q --upgrade pip
"$DEST/.venv/bin/pip" install -q numpy
"$DEST/.venv/bin/pip" install -q PySide6-Essentials

say "4/5 IBus-д бүртгэж байна"
sed "s#@DEST@#$DEST#g" "$SRC/dist/ats-ai.xml.in" | sudo tee "$COMPONENT" >/dev/null
ibus write-cache || true
mkdir -p "$HOME/.local/share/applications"
sed "s#@DEST@#$DEST#g" "$SRC/dist/ats-ai-settings.desktop.in" > "$HOME/.local/share/applications/ats-ai-settings.desktop"
mkdir -p "$HOME/.local/share/ats-ai"
[ -f "$HOME/.local/share/ats-ai/settings.json" ] || \
  printf '{"model": "%s"}\n' "$(basename "$(ls "$DEST"/models/*.npz | head -1)")" > "$HOME/.local/share/ats-ai/settings.json"

say "5/5 IBus-ийг дахин асааж байна"
ibus restart || true

cat <<'EOF'

Суулгалаа! Одоо:
  1. Settings → Keyboard → Input Sources → «+» → Mongolian → «ATS-AI (Latin to Cyrillic)» нэмнэ.
  2. Super+Space дарж ATS-AI-г сонгоод латинаар бичнэ: sain bn uu → сайн байна уу
  3. Тохиргоо: програмын жагсаалтаас «ATS-AI», эсвэл гарын icon → «Тохиргоо…»

Устгах: энэ хавтаст ./uninstall.sh
EOF
