"""ATS-AI IBus engine: type Latin, the model writes Cyrillic.

IBus starts this file (see engine/ats-ai.xml) with --ibus, using the
project's .venv Python (numpy, or torch for a .pt model). Keys work like in ATS:
letters build the word, Space or punctuation commits it, Up/Down and 1-9
pick a candidate, Enter only confirms, Esc keeps the Latin letters.

The model runs on the CPU (about 10 ms a word) so it never competes with
other GPU work. Every committed word is written to the learning history
(ats_ai/history.py) unless the field is a password or learning is paused.
"""

import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# gi comes from the system packages (python3-gi), torch from the venv.
sys.path.append("/usr/lib/python3/dist-packages")

import gi  # noqa: E402

gi.require_version("IBus", "1.0")
from gi.repository import GLib, GObject, IBus  # noqa: E402

from ats_ai.vocab import CONTEXT_WORDS  # noqa: E402
from ats_ai.typing import Typing  # noqa: E402

logging.basicConfig(
    filename=Path.home() / ".cache" / "ats-ai-engine.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Ctrl, Alt or Super held: a shortcut, not typing.
SHORTCUT_MASK = (
    IBus.ModifierType.CONTROL_MASK
    | IBus.ModifierType.MOD1_MASK
    | IBus.ModifierType.SUPER_MASK
)

# Pressing only these says nothing about the word just committed.
MODIFIER_KEYS = (
    IBus.Shift_L, IBus.Shift_R, IBus.Control_L, IBus.Control_R,
    IBus.Alt_L, IBus.Alt_R, IBus.Super_L, IBus.Super_R, IBus.Caps_Lock,
)

# Fields where nothing may be converted or remembered.
SECRET_PURPOSES = (IBus.InputPurpose.PASSWORD, IBus.InputPurpose.PIN)

# Candidates, saving and learning: the same code the Windows server runs.
TYPING = Typing()
TYPING.options("", "sain")  # load the model now, not on the first key
CONFIG = TYPING.config


class ATSAIEngine(IBus.Engine):
    __gtype_name__ = "ATSAIEngine"

    def __init__(self):
        super().__init__()
        self.buffer = ""        # Latin letters of the word being typed
        self.options = []       # Cyrillic candidates for self.buffer
        self.context = []       # last committed Cyrillic words, lowercase
        self.secret = False     # password field: pass every key through
        self.last_word = None   # (context, latin, word, how) just committed
        self.table = IBus.LookupTable.new(9, 0, True, True)

        self.pause_prop = IBus.Property.new(
            "pause", IBus.PropType.TOGGLE,
            IBus.Text.new_from_string("Суралцахыг түр зогсоох"),
            "", IBus.Text.new_from_string("Бичсэн үгсийг түүхэнд хадгалахгүй"),
            True, True, self.pause_state(), None,
        )
        self.props = IBus.PropList()
        self.props.append(self.pause_prop)
        self.props.append(IBus.Property.new(
            "settings", IBus.PropType.NORMAL,
            IBus.Text.new_from_string("Тохиргоо…"),
            "", IBus.Text.new_from_string("Миний үгс, засвар, загвар"),
            True, True, IBus.PropState.UNCHECKED, None,
        ))

    def do_process_key_event(self, keyval, keycode, state):
        """Return True when ATS-AI used the key, False to let the app have it."""
        if self.secret or state & IBus.ModifierType.RELEASE_MASK:
            return False
        if keyval == IBus.BackSpace and not self.buffer:
            self.undo_word()  # also Ctrl+Backspace; the app deletes the text
            return False
        if keyval not in MODIFIER_KEYS and not self.buffer:
            self.last_word = None  # something else came after that word
        if state & SHORTCUT_MASK:
            self.commit_word()
            return False

        char = chr(keyval) if keyval < 0x110000 else ""
        if char.isascii() and char.isalpha():
            self.buffer += char
            self.refresh()
            return True

        if not self.buffer:
            if char in ".!?" or keyval in (IBus.Return, IBus.KP_Enter):
                self.context = []  # a new sentence starts
            return False

        if keyval == IBus.BackSpace:
            self.buffer = self.buffer[:-1]
            self.refresh()
            return True
        if keyval == IBus.Escape:
            # Keep the word as typed in Latin: PLSE, git.
            self.commit_word(self.buffer, "latin")
            return True
        if keyval in (IBus.Return, IBus.KP_Enter):
            # Enter only confirms the word; press it again to send.
            self.commit_word()
            return True

        choosing = len(self.options) > 1
        if choosing and keyval in (IBus.Up, IBus.Down):
            if keyval == IBus.Up:
                self.table.cursor_up()
            else:
                self.table.cursor_down()
            self.update_lookup_table(self.table, True)
            self.show_preedit(self.current())
            return True
        if choosing and char.isdigit():
            index = int(char) - 1
            if 0 <= index < len(self.options):
                self.commit_word(self.options[index], "picked" if index else "accepted")
                return True

        # Space, punctuation, digits: send the word and the key as one text.
        # Committing the word and then passing the key on separately lets
        # some apps (Chrome, Telegram) drop or reorder the space.
        if char.isprintable() and char.isascii():
            self.commit_word(suffix=char)
            if char in ".!?":
                self.context = []
            return True

        # Arrows, Tab, Home...: confirm the word, the app handles the key.
        self.commit_word()
        self.context = []  # the cursor may be somewhere else now
        return False

    def current(self):
        """The candidate the user has selected (the first one by default)."""
        if not self.options:
            return self.buffer
        return self.options[self.table.get_cursor_pos()]

    def show_preedit(self, word):
        text = IBus.Text.new_from_string(word)
        text.append_attribute(
            IBus.AttrType.UNDERLINE, IBus.AttrUnderline.SINGLE, 0, len(word)
        )
        self.update_preedit_text(text, len(word), True)

    def refresh(self):
        """Redraw the underlined preedit and the candidate window."""
        self.table.clear()
        if not self.buffer:
            self.options = []
            self.hide_preedit_text()
            self.hide_lookup_table()
            return

        context = " ".join(self.context[-CONTEXT_WORDS:])
        self.options = TYPING.options(context, self.buffer)
        self.show_preedit(self.options[0])

        # Candidate window only when the model is unsure: дуу / дүү.
        if len(self.options) > 1:
            for option in self.options:
                self.table.append_candidate(IBus.Text.new_from_string(option))
            self.update_lookup_table(self.table, True)
        else:
            self.hide_lookup_table()

    def commit_word(self, word=None, how=None, suffix=""):
        """Send the word (default: the selected candidate) and remember it."""
        if self.buffer:
            if word is None:
                word = self.current()
                how = "picked" if self.table.get_cursor_pos() else "accepted"
            context = " ".join(self.context[-CONTEXT_WORDS:])
            latin, lower = self.buffer.lower(), word.lower()
            TYPING.commit(context, latin, lower, how)  # nothing saved while paused
            self.last_word = (context, latin, lower, how)
            if how != "latin":
                self.context = (self.context + word.lower().split())[-CONTEXT_WORDS:]
        text = (word or "") + suffix
        if text:
            self.commit_text(IBus.Text.new_from_string(text))
        self.buffer = ""
        self.refresh()

    def undo_word(self):
        """Backspace right after a commit: that word was probably wrong."""
        if self.last_word is None:
            return
        context, latin, word, how = self.last_word
        self.last_word = None
        TYPING.undo(context, latin, word, how)
        self.context = context.split()

    @property
    def paused(self):
        """Learning paused, from the input menu or the settings app."""
        return CONFIG.get("paused")

    def pause_state(self):
        return IBus.PropState.CHECKED if self.paused else IBus.PropState.UNCHECKED

    def do_focus_in(self):
        self.context = []
        self.last_word = None
        self.pause_prop.set_state(self.pause_state())  # may have changed in the app
        self.register_properties(self.props)

    def do_focus_out(self):
        # Switching windows: keep what was typed instead of losing it.
        self.commit_word()
        self.context = []
        self.last_word = None

    def do_reset(self):
        self.buffer = ""
        self.context = []
        self.last_word = None
        self.refresh()

    def do_set_content_type(self, purpose, hints):
        self.secret = purpose in SECRET_PURPOSES
        if self.secret:
            self.do_reset()

    def do_property_activate(self, name, state):
        if name == "settings":
            # Its own process: the window must never block typing.
            subprocess.Popen([sys.executable, str(ROOT / "app" / "settings.py")],
                             start_new_session=True)
            return
        if name == "pause":
            CONFIG.save(paused=state == IBus.PropState.CHECKED)
            self.pause_prop.set_state(state)
            self.update_property(self.pause_prop)
            logging.info("learning %s", "paused" if self.paused else "resumed")


def main():
    if "--ibus" not in sys.argv:
        sys.exit("This engine is started by IBus. See README for setup.")

    IBus.init()
    loop = GLib.MainLoop()
    bus = IBus.Bus()
    bus.connect("disconnected", lambda _bus: loop.quit())

    factory = IBus.Factory.new(bus.get_connection())
    factory.add_engine("ats-ai", GObject.type_from_name("ATSAIEngine"))
    bus.request_name("org.freedesktop.IBus.ATSAI", 0)

    logging.info("ATS-AI engine started")
    try:
        loop.run()
    except Exception:
        logging.exception("ATS-AI engine crashed")
        raise


if __name__ == "__main__":
    main()
