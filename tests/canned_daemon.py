# SPDX-License-Identifier: Apache-2.0
"""Sockets for the answers, and the non-answers, no fake will produce.

Three situations this client has to render correctly cannot be arranged with
the contract's scriptable fake, because the fake only ever answers things the
contract defines: a daemon that refuses the peer, a daemon that answers with an
outcome this generation does not know, and a daemon that accepts the connection
and then goes away without answering at all. All three are things a *future*, a
*misconfigured* or a *restarting* server can do, and all three have a rule in
the constitution, so all three are exercised here against a socket that does
exactly them.

They are test doubles and nothing else: they hold no policy and decide nothing.
"""

from __future__ import annotations

import json
import os
import socket
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn, UnixStreamServer

from sayfirst_contract.generation import CONTRACT_GENERATION


class _Server(ThreadingMixIn, UnixStreamServer):
    daemon_threads = True


@contextmanager
def answering(socket_path: Path, status: int, document: Mapping[str, object]) -> Iterator[Path]:
    """Serve one canned answer at a Unix socket until the context closes."""

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _reply(self) -> None:
            body = json.dumps(document).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            self._reply()

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            self._reply()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = _Server(str(socket_path), _Handler)
    os.chmod(socket_path, 0o700)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield socket_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        socket_path.unlink(missing_ok=True)


@contextmanager
def answering_by_path(
    socket_path: Path,
    routes: dict[str, tuple[int, Mapping[str, object] | Sequence[Mapping[str, object]]]],
    *,
    close_after_each: bool = False,
) -> Iterator[Path]:
    """Match the longest path prefix; advance document sequences, repeating the last.

    With `close_after_each`, every answer carries `Connection: close` and the
    server hangs up after it — what the real daemon does after an answer an
    adapter wrote (a decision read), and what a command reading twice must
    survive by reconnecting explicitly (rule C4).
    """
    prefixes = sorted(routes, key=len, reverse=True)
    positions = dict.fromkeys(prefixes, 0)

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            status, document = (
                404,
                {
                    "contract_generation": CONTRACT_GENERATION,
                    "code": "decision_not_found",
                    "message": "no canned answer for this path",
                    "retryable": False,
                },
            )
            for prefix in prefixes:
                if self.path.startswith(prefix):
                    status, documents = routes[prefix]
                    if isinstance(documents, Mapping):
                        document = documents
                    else:
                        document = documents[min(positions[prefix], len(documents) - 1)]
                        positions[prefix] += 1
                    break
            body = json.dumps(document).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if close_after_each:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = _Server(str(socket_path), _Handler)
    os.chmod(socket_path, 0o700)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield socket_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        socket_path.unlink(missing_ok=True)


@contextmanager
def hanging_up_after_accept(socket_path: Path) -> Iterator[Path]:
    """Serve a socket that accepts a connection and then closes it unanswered.

    This is the loss `connect` cannot see. The address exists, the peer
    credential is the expected one, and the verification the client does before
    it writes a byte succeeds — and only then, with the question already on the
    wire, does the far end go away. A daemon restarted, stopped or killed
    between the accept and the answer gives exactly this, and what the client
    has at that point is no answer at all, never a denial (articles 1 and 2).
    """
    stop = threading.Event()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o700)
    listener.listen(8)
    listener.settimeout(0.1)

    def accept_and_hang_up() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            # Nothing is read and nothing is written: the question is on the
            # wire and the far end is gone before the status line.
            connection.close()

    thread = threading.Thread(target=accept_and_hang_up, daemon=True)
    thread.start()
    try:
        yield socket_path
    finally:
        stop.set()
        thread.join()
        listener.close()
        socket_path.unlink(missing_ok=True)
