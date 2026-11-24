"""Talks to the ATS-AI server (server.py). Standard library only.

This file is copied into PIME's input method on Windows, where only a small
32-bit Python without pip is available, so it must not import torch,
anything from ats_ai, or any package.

If the server is not running or is slow, typing must still work: options()
then returns the Latin as typed, and commit()/undo() are dropped.
"""

import json
import os
import socket

HOST = "127.0.0.1"
PORT = int(os.environ.get("ATS_AI_PORT", "47321"))
TIMEOUT = 2.0  # seconds; a key press must never hang longer than this


class Client:
    def __init__(self, host=HOST, port=PORT, timeout=TIMEOUT):
        self.address = (host, port)
        self.timeout = timeout
        self.sock = None
        self.file = None

    def _connect(self):
        self.sock = socket.create_connection(self.address, timeout=self.timeout)
        self.file = self.sock.makefile("rwb")

    def close(self):
        for thing in (self.file, self.sock):
            try:
                if thing:
                    thing.close()
            except OSError:
                pass
        self.sock = self.file = None

    def ask(self, request):
        """The server's reply, or None if it cannot be reached."""
        data = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        for _ in range(2):  # a dropped connection gets one fresh try
            try:
                if self.sock is None:
                    self._connect()
                self.file.write(data)
                self.file.flush()
                line = self.file.readline()
                if not line:
                    raise OSError("server closed the connection")
                return json.loads(line)
            except (OSError, ValueError):
                self.close()
        return None

    def options(self, context, latin):
        reply = self.ask({"op": "options", "context": context, "latin": latin})
        if reply and isinstance(reply.get("options"), list) and reply["options"]:
            return reply["options"]
        return [latin]

    def commit(self, context, latin, word, how):
        self.ask({"op": "commit", "context": context, "latin": latin, "word": word, "how": how})

    def undo(self, context, latin, word, how):
        self.ask({"op": "undo", "context": context, "latin": latin, "word": word, "how": how})

    def alive(self):
        reply = self.ask({"op": "ping"})
        return bool(reply and reply.get("ok"))
