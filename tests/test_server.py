"""ats_ai/server.py and client.py over a real local socket."""

import threading

from ats_ai.client import Client
from ats_ai.server import answer, make_server


class FakeTyping:
    paused = False

    def __init__(self):
        self.calls = []

    def options(self, context, latin):
        return {"duu": ["дуу", "дүү"]}.get(latin, [latin])

    def commit(self, *args):
        self.calls.append(("commit",) + args)

    def undo(self, *args):
        self.calls.append(("undo",) + args)


def serve(typing):
    server = make_server(typing, port=0)  # any free port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def test_round_trip():
    typing = FakeTyping()
    server, port = serve(typing)
    try:
        client = Client(port=port)
        assert client.alive()
        assert client.options("", "duu") == ["дуу", "дүү"]
        client.commit("миний", "duu", "дүү", "picked")
        client.undo("миний", "duu", "дүү", "picked")
        assert typing.calls == [("commit", "миний", "duu", "дүү", "picked"),
                                ("undo", "миний", "duu", "дүү", "picked")]
        client.close()
    finally:
        server.shutdown()
        server.server_close()


def test_bad_requests_get_an_error_and_the_server_lives():
    typing = FakeTyping()
    server, port = serve(typing)
    try:
        client = Client(port=port)
        assert "error" in client.ask({"op": "nope"})
        assert "error" in client.ask({"op": "commit", "latin": "x"})
        assert "error" in client.ask({"op": "commit", "context": "", "latin": "a",
                                      "word": "а", "how": "rm -rf"})
        assert client.options("", "duu") == ["дуу", "дүү"]
    finally:
        server.shutdown()
        server.server_close()


def test_no_server_keeps_latin():
    client = Client(port=1, timeout=0.2)  # nothing listens there
    assert client.options("", "Sain") == ["Sain"]
    client.commit("", "sain", "сайн", "accepted")  # dropped, no error
    assert not client.alive()


def test_answer_ping():
    assert answer(FakeTyping(), {"op": "ping"}) == {"ok": True, "paused": False}
