"""Put ATS-AI into an installed PIME (Windows, for testing before an installer).

Run from the repo, in a terminal opened "as administrator" (PIME lives in
Program Files):

    py pime\\install.py

It copies pime\\ats_ai\\ and ats_ai\\client.py to
    C:\\Program Files (x86)\\PIME\\python\\input_methods\\ats_ai\\
and restarts PIME so it loads the new code. Run it again after any change.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIME = Path(os.environ.get("PIME_DIR", r"C:\Program Files (x86)\PIME"))
TARGET = PIME / "python" / "input_methods" / "ats_ai"


def main():
    if not (PIME / "python" / "input_methods").is_dir():
        sys.exit(f"PIME not found at {PIME}. Install PIME first, or set PIME_DIR.")
    TARGET.mkdir(exist_ok=True)
    for name in ("ime.json", "ats_ime.py", "logic.py", "icon.ico"):
        shutil.copy2(REPO / "pime" / "ats_ai" / name, TARGET / name)
    shutil.copy2(REPO / "ats_ai" / "client.py", TARGET / "client.py")
    (TARGET / "__init__.py").touch()
    print(f"copied to {TARGET}")

    launcher = PIME / "PIMELauncher.exe"
    if launcher.exists():
        subprocess.run([str(launcher), "/quit"], check=False)
        subprocess.Popen([str(launcher)])
        print("PIME restarted")
    else:
        print("PIMELauncher.exe not found: sign out and in again to reload PIME")


if __name__ == "__main__":
    main()
