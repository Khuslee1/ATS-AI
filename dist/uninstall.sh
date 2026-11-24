#!/usr/bin/env bash
# ATS-AI-г устгана. Таны үгс, түүх (~/.local/share/ats-ai) үлдэнэ — хүсвэл гараар устгана.
set -euo pipefail
sudo rm -f /usr/share/ibus/component/ats-ai.xml
ibus write-cache || true
rm -f "$HOME/.local/share/applications/ats-ai-settings.desktop"
rm -rf "$HOME/.local/opt/ats-ai"
ibus restart || true
echo "ATS-AI устгагдлаа. Settings → Keyboard-оос ATS-AI-г хасна уу."
echo "Таны түүх, үгс: ~/.local/share/ats-ai (устгах бол: rm -r ~/.local/share/ats-ai)"
