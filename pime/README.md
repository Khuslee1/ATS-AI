# ATS-AI on Windows (PIME)

Two parts:

- **The server** (`ats_ai/server.py`) — the model, your words, history and settings.
  A normal 64-bit Python with numpy (no torch). Listens on `127.0.0.1:47321` only.
- **The input method** (`pime/ats_ai/`) — runs inside PIME's small 32-bit Python,
  handles keys and asks the server. Without the server it keeps typing in Latin.

## Test on a Windows laptop (before there is an installer)

1. Install **Python 3.12, 64-bit** from python.org (tick "Add python.exe to PATH"),
   **Git**, and **PIME 1.3.0** (`PIME-1.3.0-stable-setup.exe` from
   https://github.com/EasyIME/PIME/releases).
2. Get the repo and its Python packages:
   ```
   git clone <repo> ATS-AI
   cd ATS-AI
   py -m venv .venv
   .venv\Scripts\pip install numpy PySide6-Essentials
   ```
   Copy `models\v5.npz` from the Linux machine (models are not in git).
3. Start the server and leave the window open:
   ```
   .venv\Scripts\python -m ats_ai.server
   ```
   It is ready when it prints `ATS-AI server on 127.0.0.1:47321`.
4. In a terminal opened **as administrator**, in the repo folder:
   ```
   py pime\install.py
   ```
5. Settings › Time & language › Language & region › Mongolian › Keyboards › add **ATS-AI**.
   Switch to it with Win+Space and type in Notepad: `sain bn uu`.

## Logs

- Server: the window from step 3.
- PIME's Python side: `%LOCALAPPDATA%\PIME\Logs\python_backend.log`
- PIME live debug: `"C:\Program Files (x86)\PIME\PIMELauncher.exe" /console`

Where files live on Windows: history, settings, labels in `%USERPROFILE%\.local\share\ats-ai\`
(the same code as Linux; may move to `%APPDATA%` later).
