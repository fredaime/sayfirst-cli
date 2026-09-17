# SPDX-License-Identifier: Apache-2.0
"""The HTTP connection, faked, for the reads that do not need a socket.

Peer verification belongs to the socket tests in `canned_daemon.py`. What this
double is for is everything a socket cannot show cheaply: which targets a walk
asked for, in which order, how many times the caller re-verified the far end,
and whether the connection was closed at the end. It lives in a module of its
own because three test files need it, and a test module that imports a fixture
out of a neighbouring test module makes both of them one file.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from sayfirst_contract.transport.peer import PeerCredential
from sayfirst_contract.transport.socket_client import VerifiedConnection


class Replies:
    """Scripted answers, and the two things `VerifiedConnection.reconnect()`
    needs from a real connection — a `connect()` that verifies the far end
    again, counted here as `reconnects`, and the credential it leaves behind."""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = False
        self.reconnects = 0
        self.last_credential = PeerCredential(1000, 1000, 1, "instant")
        self.last_expected_uid = 1000

    def connect(self):
        self.reconnects += 1
        self.closed = False

    def request(self, method, target, body, headers):
        self.requests.append((method, target, body))

    def getresponse(self):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        status, document = response
        # A `bytes` document is served exactly as given, so a reply only the
        # client has to parse can be arranged — a depth that would overflow
        # this double's own encoder before the client ever saw it.
        body = document if isinstance(document, bytes) else json.dumps(document).encode()
        return SimpleNamespace(status=status, read=lambda: body)

    def close(self):
        self.closed = True


def verified(profile, http: Replies) -> VerifiedConnection:
    """The connection the client would hold after a verified `connect`."""
    return VerifiedConnection(profile, PeerCredential(1000, 1000, 1, "instant"), 1000, http)
