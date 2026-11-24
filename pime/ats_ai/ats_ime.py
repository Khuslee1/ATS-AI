"""ATS-AI for Windows: PIME's TextService around logic.py.

PIME (https://github.com/EasyIME/PIME) loads this from
    <PIME>\\python\\input_methods\\ats_ai\\
with its own small 32-bit Python, so only the standard library is used.
The model runs in the ATS-AI server (ats_ai/server.py); client.py talks to it
and keeps typing in Latin if the server is not running.

PIME asks twice per key: filterKeyDown ("will you take this key?") and, only
if we said yes, onKeyDown ("do it"). A key we let through can still have an
effect first (commit the word before Ctrl+C or an arrow), so those run in
filterKeyDown, which then answers no.
"""

from textService import TextService

from .client import Client
from .logic import Logic

VK_NAMES = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x1B: "escape",
    0x10: "shift", 0x11: "ctrl", 0x12: "alt", 0x14: "capslock",
    0x25: "left", 0x26: "up", 0x27: "right", 0x28: "down",
    0x21: "pageup", 0x22: "pagedown", 0x23: "end", 0x24: "home", 0x2E: "delete",
}
VK_CONTROL, VK_MENU = 0x11, 0x12


class Screen:
    """logic.Screen on top of PIME's setters."""

    def __init__(self, service):
        self.service = service

    def show(self, composition, candidates, cursor):
        s = self.service
        s.setCompositionString(composition)
        s.setCompositionCursor(len(composition))
        if candidates:
            s.setCandidateList(candidates)
            s.setCandidateCursor(cursor)
            s.setShowCandidates(True)
        else:
            s.setShowCandidates(False)

    def commit(self, text):
        self.service.setCommitString(text)


class ATSTextService(TextService):
    def __init__(self, client):
        TextService.__init__(self, client)
        self.logic = Logic(Client(), Screen(self))

    def onActivate(self):
        TextService.onActivate(self)
        self.customizeUI(candPerRow=1, candUseCursor=True)
        self.setSelKeys("123456789")

    def onDeactivate(self):
        self.logic.reset()
        TextService.onDeactivate(self)

    def _key(self, keyEvent):
        key = VK_NAMES.get(keyEvent.keyCode, "")
        char = chr(keyEvent.charCode) if keyEvent.charCode else ""
        shortcut = keyEvent.isKeyDown(VK_CONTROL) or keyEvent.isKeyDown(VK_MENU)
        if shortcut or not char.isprintable():
            char = ""
        return key, char, shortcut

    def filterKeyDown(self, keyEvent):
        key, char, shortcut = self._key(keyEvent)
        if self.logic.wants(key, char, shortcut):
            return True  # onKeyDown does it
        self.logic.press(key, char, shortcut)  # side effects only; the app gets the key
        return False

    def onKeyDown(self, keyEvent):
        key, char, shortcut = self._key(keyEvent)
        return self.logic.press(key, char, shortcut)

    def onCompositionTerminated(self, forced):
        # The app ended the word (a click elsewhere): it keeps the text shown.
        self.logic.drop()
