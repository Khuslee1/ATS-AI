#!/usr/bin/env bash
# Build dist/out/ats-ai_<version>_all.deb — install with a double-click (App Center).
#   dist/build_deb.sh              (model chosen in settings, else the newest .npz)
#   MODEL=v5 dist/build_deb.sh
# Uses Ubuntu's own Python, numpy, PyGObject and PySide6 (no venv, no pip).
# Never packs your history, labels, settings or my_words.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${MODEL:-$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.local/share/ats-ai/settings.json"))).get("model",""))' 2>/dev/null || true)}"
MODEL="${MODEL%.*}"
[ -n "$MODEL" ] && [ -f "$REPO/models/$MODEL.npz" ] || MODEL="$(basename "$(ls -t "$REPO"/models/*.npz | head -1)" .npz)"
NPZ="$REPO/models/$MODEL.npz"
[ -f "$NPZ" ] || { echo "No $NPZ — run: .venv/bin/python tools/export_weights.py models/$MODEL.pt"; exit 1; }

VERSION="0.1.$(date +%Y%m%d%H%M)"
OUT="$REPO/dist/out"
ROOT="$(mktemp -d)/ats-ai"
APP="$ROOT/opt/ats-ai"
mkdir -p "$APP"/{ats_ai,engine,app,models,data} "$ROOT/DEBIAN" "$OUT" \
         "$ROOT/usr/share/ibus/component" "$ROOT/usr/share/applications" \
         "$ROOT/usr/share/icons/hicolor/64x64/apps" "$ROOT/usr/share/doc/ats-ai"

# The program: what the input method and the settings window need, nothing for training.
for f in client config history personal share typing vocab words numpy_model server; do
    cp "$REPO/ats_ai/$f.py" "$APP/ats_ai/"
done
cp "$REPO/engine/main.py" "$APP/engine/"
cp "$REPO/app/settings.py" "$REPO/app/icon.png" "$REPO/dist/ats-ai-settings" "$REPO/dist/get-qt" "$APP/app/"
cp "$NPZ" "$APP/models/"
cp "$REPO/data/abbreviations.tsv" "$APP/data/"
cp "$REPO/app/icon.png" "$ROOT/usr/share/icons/hicolor/64x64/apps/ats-ai.png"
cp "$REPO/dist/README-mn.txt" "$ROOT/usr/share/doc/ats-ai/"

sed -e "s#@DEST@/.venv/bin/python#/usr/bin/python3#; s#@DEST@#/opt/ats-ai#g" \
    "$REPO/dist/ats-ai.xml.in" > "$ROOT/usr/share/ibus/component/ats-ai.xml"
sed -e "s#^Exec=.*#Exec=/opt/ats-ai/app/ats-ai-settings#; s#@DEST@/app/icon.png#ats-ai#; s#@DEST@#/opt/ats-ai#g" \
    "$REPO/dist/ats-ai-settings.desktop.in" > "$ROOT/usr/share/applications/ats-ai-settings.desktop"

SIZE=$(du -sk "$ROOT" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<EOF
Package: ats-ai
Version: $VERSION
Architecture: all
Maintainer: Khuslee <noreply@example.invalid>
Installed-Size: $SIZE
Depends: python3 (>= 3.12), python3-numpy, python3-gi, gir1.2-ibus-1.0, ibus, python3-pip, zenity, pkexec | policykit-1, libxcb-cursor0
Recommends: python3-pyside6.qtwidgets, python3-pyside6.qtgui, python3-pyside6.qtcore
Section: utils
Priority: optional
Description: Mongolian: type in Latin letters, get Cyrillic (IBus)
 A small model turns chat-style Latin (sain bn uu) into Cyrillic (сайн байна уу).
 After installing: log out and in (or run "ibus restart"), then
 Settings > Keyboard > Input Sources > + > Mongolian > ATS-AI.
 Your words and history stay in ~/.local/share/ats-ai and are never sent anywhere.
EOF
cat > "$ROOT/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
ibus write-cache --system 2>/dev/null || true
gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
# The settings window needs Qt. Ubuntu 25.04+ installs it as a package
# (Recommends); 24.04 has none, so fetch it now. Typing works without it, and
# the settings launcher offers the download again if this fails (no internet).
if ! PYTHONPATH=/opt/ats-ai/lib python3 -c "import PySide6.QtWidgets" 2>/dev/null; then
    echo "ATS-AI: downloading Qt for the settings window (~100 MB)..."
    /opt/ats-ai/app/get-qt || echo "ATS-AI: could not download Qt now; the settings window will offer it later."
fi
exit 0
EOF
cat > "$ROOT/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
case "$1" in
    remove|purge) rm -rf /opt/ats-ai/lib ;;  # Qt fetched by postinst, not a packaged file
esac
ibus write-cache --system 2>/dev/null || true
exit 0
EOF
chmod 755 "$ROOT/DEBIAN/postinst" "$ROOT/DEBIAN/postrm"
find "$ROOT/opt" "$ROOT/usr" -type d -exec chmod 755 {} +
find "$ROOT/opt" "$ROOT/usr" -type f -exec chmod 644 {} +
chmod 755 "$APP/app/ats-ai-settings" "$APP/app/get-qt"

DEB="$OUT/ats-ai_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$ROOT" "$DEB" >/dev/null
rm -rf "$(dirname "$ROOT")"
echo "$DEB  (model $MODEL, $(du -h "$DEB" | cut -f1))"
