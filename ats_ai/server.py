"""ATS-AI server: the model and the user's words behind a local socket.

On Windows the input method runs inside PIME's own small 32-bit Python,
which cannot load the model. This server runs in a normal 64-bit Python
(later a packaged .exe) and does the work; PIME only asks it.

    python -m ats_ai.server            (port 47321, or ATS_AI_PORT)

Only 127.0.0.1 is listened on: nothing outside this computer can connect.
One JSON object per line in each direction:

    {"op": "options", "context": "миний", "latin": "duu"} -> {"options": ["дүү", "дуу"]}
    {"op": "commit", "context": ..., "latin": ..., "word": ..., "how": "picked"} -> {"ok": true}
    {"op": "undo",   same fields as commit}                               -> {"ok": true}
    {"op": "ping"}                                -> {"ok": true, "paused": false}

A bad request gets {"error": "..."}; the server keeps running.
"""

import json
import logging
import os
import socketserver
import threading

from ats_ai.typing import Typing

HOST = "127.0.0.1"
PORT = int(os.environ.get("ATS_AI_PORT", "47321"))
FIELDS = ("context", "latin", "word", "how")


def answer(typing, request):
    """The reply for one request (a dict); raises ValueError on a bad one."""
    op = request.get("op")
    if op == "ping":
        return {"ok": True, "paused": typing.paused}
    if op == "options":
        return {"options": typing.options(str(request.get("context", "")), str(request["latin"]))}
    if op in ("commit", "undo"):
        args = [str(request[f]) for f in FIELDS]
        if args[3] not in ("accepted", "picked", "latin"):
            raise ValueError(f"bad how: {args[3]}")
        (typing.commit if op == "commit" else typing.undo)(*args)
        return {"ok": True}
    raise ValueError(f"unknown op: {op}")


def make_server(typing, host=HOST, port=PORT):
    lock = threading.Lock()  # one model, one history file

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            for line in self.rfile:
                try:
                    request = json.loads(line)
                    with lock:
                        reply = answer(typing, request)
                except (ValueError, KeyError, TypeError) as error:
                    reply = {"error": str(error)}
                except Exception as error:  # never let one request stop the server
                    logging.exception("request failed")
                    reply = {"error": str(error)}
                self.wfile.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    return Server((host, port), Handler)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    typing = Typing()
    typing.options("", "sain")  # load the model now, not on the first key
    with make_server(typing) as server:
        logging.info("ATS-AI server on %s:%d", HOST, PORT)
        server.serve_forever()


if __name__ == "__main__":
    main()
