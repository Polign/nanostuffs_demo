"""The agent behind the Next.js chat: HTTP in front of chat.py.

This is the piece that runs on the EC2 instance in the Nanostuffs setup. The
Next.js route handler forwards {userId, message} here; this process keeps one
Recall client per person and answers with the whole turn as JSON, so the UI
can show what memory knew, the query, the hits and what was remembered.

    python agent/server.py      # http://127.0.0.1:8000
    POST /chat     {"userId": "priya", "message": "...", "memory": true}
    GET  /history?userId=priya  what Recall holds, with what each value replaced
    POST /reset    {"userId": "priya"}   forget everything about this person (demo only)
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from qdrant_client import QdrantClient

import chat

HOST = os.environ.get("AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("AGENT_PORT", "8000"))

_assistants: dict[tuple[str, bool], chat.Assistant] = {}
_locks: dict[tuple[str, bool], threading.Lock] = {}
_registry_lock = threading.Lock()


def assistant(user: str, memory: bool) -> tuple[chat.Assistant, threading.Lock]:
    key = (user, memory)
    with _registry_lock:
        if key not in _assistants:
            _assistants[key] = chat.Assistant(user, memory=memory)
            _locks[key] = threading.Lock()
        return _assistants[key], _locks[key]


def history(user: str) -> list[dict]:
    a, lock = assistant(user, True)
    with lock:
        out = []
        for mem in a.memory.ask("everything known about the person"):
            out.append({"text": mem.text, "replaced": [b.text for b in mem.before], "days_ago": mem.days_ago})
        return out


def reset(user: str) -> None:
    """Drops the person's memory collection. Demo convenience, not a product
    operation: Recall itself never deletes."""
    with _registry_lock:
        for memory in (True, False):
            a = _assistants.pop((user, memory), None)
            _locks.pop((user, memory), None)
            if a:
                a.close()
    QdrantClient(url=chat.QDRANT_URL, api_key=os.environ.get("QDRANT_API_KEY")).delete_collection(f"{chat.MEMORY}_text_{user}")


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, body: dict | list) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/healthz":
            return self._json(200, {"ok": True})
        if url.path == "/history":
            user = (parse_qs(url.query).get("userId") or [""])[0].strip().lower()
            if not user:
                return self._json(400, {"error": "userId is required"})
            return self._json(200, {"user": user, "memories": history(user)})
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        try:
            body = self._body()
        except ValueError:
            return self._json(400, {"error": "body must be JSON"})
        user = str(body.get("userId") or "").strip().lower()
        if not user:
            return self._json(400, {"error": "userId is required"})
        if url.path == "/reset":
            reset(user)
            return self._json(200, {"ok": True})
        if url.path != "/chat":
            return self._json(404, {"error": "not found"})
        message = str(body.get("message") or "").strip()
        if not message:
            return self._json(400, {"error": "message is required"})
        a, lock = assistant(user, bool(body.get("memory", True)))
        with lock:
            try:
                self._json(200, a.respond(message))
            except Exception as exc:  # the UI shows the error instead of hanging
                self._json(500, {"error": str(exc)[:500]})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"agent listening on http://{HOST}:{PORT} (Qdrant {chat.QDRANT_URL}, extraction {chat.EXTRACT_MODEL}, chat {chat.MODEL})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for a in _assistants.values():
            a.close()


if __name__ == "__main__":
    main()
