"""Key handling for the Windows input method, without PIME.

The same rules as the Linux engine (engine/main.py), written against a tiny
"screen" interface so it can be tested on Linux with a fake one:

    screen.show(composition, candidates, cursor)   underlined word + list
    screen.commit(text)                            send text to the app

press(key, char) returns True when ATS-AI used the key, False to let the
application have it. key is one of the names below or "" for a plain
character; char is the typed character ("" for none).

Standard library only: PIME runs a small 32-bit Python without pip.
"""

CONTEXT_WORDS = 2
MODIFIERS = ("shift", "ctrl", "alt", "capslock")  # pressed alone: nothing to do

LETTERS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
SENTENCE_END = ".!?"


class Logic:
    def __init__(self, client, screen):
        self.client = client    # options / commit / undo (ats_ai/client.py)
        self.screen = screen
        self.buffer = ""        # Latin letters of the word being typed
        self.options = []       # candidates for self.buffer
        self.cursor = 0         # selected candidate
        self.context = []       # last committed Cyrillic words, lowercase
        self.last_word = None   # (context, latin, word, how) just committed

    # --- keys -----------------------------------------------------------------

    def wants(self, key, char="", shortcut=False):
        """Would press() use this key? No side effects (PIME asks first)."""
        if key in MODIFIERS or shortcut:
            return False
        if char in LETTERS:
            return True
        if not self.buffer:
            return False
        if key in ("backspace", "escape", "enter"):
            return True
        if len(self.options) > 1:
            if key in ("up", "down"):
                return True
            if char.isdigit() and 0 <= int(char) - 1 < len(self.options):
                return True
        return bool(char) and char.isprintable() and char.isascii()

    def press(self, key, char="", shortcut=False):
        if key in MODIFIERS and not shortcut:
            return False  # Shift for a capital letter must not end the word
        if key == "backspace" and not self.buffer:
            self.undo_word()  # the app deletes the text itself
            return False
        if not self.buffer:
            self.last_word = None  # something else came after that word
        if shortcut:  # Ctrl / Alt held
            self.commit_word()
            return False

        if char in LETTERS:
            self.buffer += char
            self.refresh()
            return True

        if not self.buffer:
            if char and char in SENTENCE_END or key == "enter":
                self.context = []  # a new sentence starts
            return False

        if key == "backspace":
            self.buffer = self.buffer[:-1]
            self.refresh()
            return True
        if key == "escape":
            self.commit_word(self.buffer, "latin")  # keep as typed: PLSE, git
            return True
        if key == "enter":
            self.commit_word()  # Enter only confirms; press again to send
            return True

        choosing = len(self.options) > 1
        if choosing and key in ("up", "down"):
            step = -1 if key == "up" else 1
            self.cursor = (self.cursor + step) % len(self.options)
            self.draw()
            return True
        if choosing and char.isdigit():
            index = int(char) - 1
            if 0 <= index < len(self.options):
                self.commit_word(self.options[index], "picked" if index else "accepted")
                return True

        # Space, punctuation, digits: the word and the key as one text.
        if char and char.isprintable() and char.isascii():
            self.commit_word(suffix=char)
            if char in SENTENCE_END:
                self.context = []
            return True

        # Arrows, Tab, Home...: confirm the word, the app handles the key.
        self.commit_word()
        self.context = []  # the cursor may be somewhere else now
        return False

    def drop(self):
        """The app ended the word itself; it keeps what was shown."""
        self.buffer, self.options, self.cursor = "", [], 0

    def reset(self):
        """Focus moved: keep what was typed instead of losing it."""
        self.commit_word()
        self.context = []
        self.last_word = None

    # --- words ----------------------------------------------------------------

    def _context(self):
        return " ".join(self.context[-CONTEXT_WORDS:])

    def current(self):
        return self.options[self.cursor] if self.options else self.buffer

    def refresh(self):
        self.cursor = 0
        self.options = self.client.options(self._context(), self.buffer) if self.buffer else []
        self.draw()

    def draw(self):
        if not self.buffer:
            self.screen.show("", [], 0)
        else:
            # The list only when there is a choice: дуу / дүү.
            self.screen.show(self.current(), self.options if len(self.options) > 1 else [], self.cursor)

    def commit_word(self, word=None, how=None, suffix=""):
        if self.buffer:
            if word is None:
                word = self.current()
                how = "picked" if self.cursor else "accepted"
            context, latin, lower = self._context(), self.buffer.lower(), word.lower()
            self.client.commit(context, latin, lower, how)
            self.last_word = (context, latin, lower, how)
            if how != "latin":
                self.context = (self.context + lower.split())[-CONTEXT_WORDS:]
        text = (word or "") + suffix
        self.buffer = ""
        self.options = []
        self.cursor = 0
        self.draw()
        if text:
            self.screen.commit(text)

    def undo_word(self):
        if self.last_word is None:
            return
        context, latin, word, how = self.last_word
        self.last_word = None
        self.client.undo(context, latin, word, how)
        self.context = context.split()
