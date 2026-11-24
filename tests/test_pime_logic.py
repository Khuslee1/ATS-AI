"""pime/ats_ai/logic.py: the Windows key handling, with a fake server and screen."""

import importlib.util
import itertools
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pime_logic", Path(__file__).resolve().parent.parent / "pime" / "ats_ai" / "logic.py")
logic_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(logic_module)
Logic = logic_module.Logic


class FakeClient:
    def __init__(self):
        self.log = []

    def options(self, context, latin):
        table = {"duu": ["дуу", "дүү"], "sain": ["сайн"], "minii": ["миний"], "git": ["гит"]}
        out = table.get(latin.lower(), [latin])
        return [o.capitalize() for o in out] if latin[:1].isupper() else out

    def commit(self, *args):
        self.log.append(("commit",) + args)

    def undo(self, *args):
        self.log.append(("undo",) + args)


class FakeScreen:
    def __init__(self):
        self.text = ""          # what the app has received
        self.composition = ""
        self.candidates = []

    def show(self, composition, candidates, cursor):
        self.composition, self.candidates = composition, candidates

    def commit(self, text):
        self.text += text


def setup():
    client, screen = FakeClient(), FakeScreen()
    return Logic(client, screen), client, screen


def type_text(logic, text):
    for ch in text:
        if not logic.press("", ch):
            logic.screen.commit(ch)  # a key we let through: the app types it


def test_word_then_space():
    logic, client, screen = setup()
    type_text(logic, "sain")
    assert (screen.composition, screen.text) == ("сайн", "")
    logic.press("", " ")
    assert (screen.composition, screen.text) == ("", "сайн ")
    assert client.log == [("commit", "", "sain", "сайн", "accepted")]


def test_choice_list_and_context():
    logic, client, screen = setup()
    type_text(logic, "minii duu")
    assert screen.candidates == ["дуу", "дүү"]
    assert logic.press("down")
    assert screen.composition == "дүү"
    logic.press("", " ")
    assert screen.text == "миний дүү "
    assert client.log[-1] == ("commit", "миний", "duu", "дүү", "picked")


def test_digit_picks_escape_keeps_latin_backspace_undoes():
    logic, client, screen = setup()
    type_text(logic, "duu")
    logic.press("", "2")
    assert screen.text == "дүү"
    type_text(logic, " git")
    logic.press("escape")
    assert screen.text == "дүү git"
    assert client.log[-1] == ("commit", "дүү", "git", "git", "latin")
    assert logic.press("backspace") is False      # the app deletes; we take it back
    assert client.log[-1] == ("undo", "дүү", "git", "git", "latin")


def test_shift_does_not_end_the_word_and_case_is_kept():
    logic, _, screen = setup()
    logic.press("shift")
    logic.press("", "S")
    logic.press("shift")
    type_text(logic, "ain")
    assert screen.composition == "Сайн"


def test_backspace_inside_word_and_shortcut_commits():
    logic, _, screen = setup()
    type_text(logic, "saii")
    logic.press("backspace")
    assert logic.buffer == "sai"
    type_text(logic, "n")
    assert logic.press("", "", shortcut=True) is False   # Ctrl+C: word first, then the app
    assert screen.text == "сайн"


def test_wants_agrees_with_press():
    keys = ["", "backspace", "escape", "enter", "up", "down", "left", "tab", "shift"]
    chars = ["", "a", "S", " ", ".", "2", "5"]
    for prefix in ["", "sai", "duu"]:
        for key, char, shortcut in itertools.product(keys, chars, [False, True]):
            if key and char:
                continue
            logic, _, _ = setup()
            type_text(logic, prefix)
            said = logic.wants(key, char, shortcut)
            assert logic.press(key, char, shortcut) == said, (prefix, key, char, shortcut)
