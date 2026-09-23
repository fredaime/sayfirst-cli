# SPDX-License-Identifier: Apache-2.0
"""Ask before an HTTP request leaves the process, and record what came back.

Governs `urllib.request.urlopen` — the one attribute this pack's point names.
It is the one function every scheme `urllib.request` handles goes through —
`http`, `https`, `file` and `data` alike, and every higher-level call the
standard library builds on top of it too — so a `file:` or `data:` read is
asked under this pack's capability as well, since the interpreter offers no
narrower seam than this one function; the URL in the digest is what
distinguishes them.

`url` — the address the call is asked to open, rendered as the text it names
whatever shape the caller passed it in — is the one argument sent to the
boundary. Nothing else of the call is sent (article 11: what is sent is a
digest, and which arguments it covers is declared, never implicit).

**As text, whatever the caller's type.** The call accepts a plain string, or a
`Request` object built up with headers and a method of its own; a `Request`
carries the address it will open under `full_url`, so that is read out rather
than rendering the object itself, which would give its `repr` and not the
address.

The wrapper is a plain function, so what it returns is the real response
object, never a stand-in for it.

**A redirect is a second request, and wrapping the one function does not see
it.** One `urlopen` of an address that answers `302` makes two requests, and
the second one is not a second call to `urlopen`: the standard library's
redirect handler goes back through the OPENER it is attached to. So a pack
that asked only where `urlopen` was called asked about the first address and
let the second request leave the process with no question put about it — while
the interpreter reported both, as two `urllib.Request` events, which is the
event this pack's manifest names for a verifier. The two shipped halves then
disagreed about an ordinary redirect: the primary mode let the second request
through ungoverned, and the verifier, reading one decision against two events,
aborted it as ungoverned. Neither half was wrong about what it saw.

So for the length of one governed `urlopen` call, and no longer, the opener's
own `open` is governed too: the first of them is the request `urlopen` was
already asked about, and every one after it is a request the redirect
machinery made, each asked about under the same capability with its own
address. That puts exactly one ask against exactly one `urllib.Request` event
— which is the arithmetic the verifier does — for a redirect of any length,
and whatever host or scheme a hop moves to, since the address asked about is
the one the handler resolved.

**It is the opener's `open` and not its redirect handler**, because that is
where the interpreter reports the event, and because a handler is an object an
opener was built with: an opener built before this pack was installed holds the
handler it was built with, and replacing the class would not reach it. `open`
is looked up on the opener's class at each call, so an opener built at any time
— before the engine ran, during the program's own imports, or never at all
because `urlopen` built the default one itself — goes through this.

**Put back, always.** The governed `open` is in place only while at least one
governed `urlopen` call is in flight, is counted across threads so concurrent
calls do not restore it under each other, and is removed in a `finally`. A
call made on an opener directly, outside any `urlopen`, is not asked about —
the same requests that were not asked about before this — and a verifier
watching the same events says so as a finding rather than this pack pretending
otherwise.

**What an outcome means across a redirect.** The recorded outcome is the status
of the response the ask's own request produced; for the request `urlopen`
started, that is the status the caller is handed, which after a redirect is the
final one. Each hop records the status its own `open` returned. Neither is
invented, and no ask is left with a status that belongs to another request.
"""

from __future__ import annotations

import hashlib
import inspect
import threading
from contextlib import contextmanager

#: `urllib.request.OpenerDirector.open` exactly as this module found it, taken
#: once and never cleared, so that restoring it is giving back the very object
#: that was taken and never one that merely resembles it.
_THE_REAL_OPEN = None

#: How many governed calls are in flight, across every thread. The governed
#: `open` goes in on the way from none to one and comes out on the way back.
_IN_FLIGHT = 0

_LOCK = threading.Lock()

#: The governed calls this thread is inside, innermost last. Per thread,
#: because a redirect is followed on the thread that started the request, and
#: because a call another thread makes on an opener of its own is not this
#: call's second request.
_CALLS = threading.local()


class _Call:
    """One governed `urlopen` call: whom to ask, and whether its own request is past."""

    __slots__ = ("boundary", "capability", "entry_pending")

    def __init__(self, capability, boundary):
        self.capability = capability
        self.boundary = boundary
        #: The first `open` of this call is the request the wrapper already
        #: asked about. Asking again there would put two questions to the
        #: boundary for one request.
        self.entry_pending = True


def wrap(original, capability, boundary):
    """Bind the call to `original`'s own signature, ask, open, and record the status.

    The ask carries `url` rendered as text — a `Request`'s own address, or
    `str()` of whatever else was passed — so the digest is computable
    whichever shape the caller called with.

    The opener is governed around the call, not around the ask: a refusal
    arrives out of `boundary.request` before anything is opened, and then there
    is no request to follow a redirect of.
    """
    signature = inspect.signature(original)

    def wrapper(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        arguments = {"url": _rendered(bound.arguments.get("url"))}
        with boundary.request(capability, arguments) as handle:
            with _following_the_redirects(capability, boundary):
                response = original(*args, **kwargs)
            status = getattr(response, "status", None)
            if status is not None:
                # Nothing more of the response is worth an outcome: the status
                # is what the digest names, and nothing else of the response
                # is sent anywhere. `hasattr` alone is not enough: a `file:`
                # or `data:` read returns `urllib.response.addinfourl`, which
                # HAS a `status` attribute that is always `None` — recording a
                # digest for it would claim an outcome the response does not
                # have (`sha256("status:None")` looks like a real status to
                # anything reading the chain back).
                handle.record_outcome(_status_digest(status))
            return response

    return wrapper


@contextmanager
def _following_the_redirects(capability, boundary):
    """Govern the opener's own `open` for the length of one `urlopen` call."""
    call = _Call(capability, boundary)
    _began(call)
    try:
        yield
    finally:
        _ended()


def _stack():
    """This thread's governed calls, innermost last."""
    calls = getattr(_CALLS, "calls", None)
    if calls is None:
        calls = []
        _CALLS.calls = calls
    return calls


def _began(call):
    global _IN_FLIGHT, _THE_REAL_OPEN
    # Imported here and not at the top of the file: a point may name a module
    # the program has not loaded yet, and the engine loads this file to build
    # the wrapper BEFORE that happens. Importing it up here would load it on
    # the pack's behalf and take that case away from the engine. By the time a
    # governed call is made, the module is loaded — the call is in it.
    import urllib.request

    with _LOCK:
        if _THE_REAL_OPEN is None:
            _THE_REAL_OPEN = urllib.request.OpenerDirector.open
        if _IN_FLIGHT == 0:
            urllib.request.OpenerDirector.open = _asking_open
        _IN_FLIGHT += 1
    _stack().append(call)


def _ended():
    global _IN_FLIGHT
    import urllib.request

    _stack().pop()
    with _LOCK:
        _IN_FLIGHT -= 1
        if _IN_FLIGHT == 0:
            urllib.request.OpenerDirector.open = _THE_REAL_OPEN


def _asking_open(self, *args, **kwargs):
    """The opener's `open`, asked about unless it is the call's own first request.

    Reached three ways, and each is answered on what the thread is inside of:
    the request `urlopen` made, which was asked about a moment ago and is let
    through here; a request the redirect machinery made, which is asked about;
    and a call on an opener made outside any governed `urlopen`, which is
    neither this pack's to ask about nor its to change.
    """
    calls = _stack()
    if not calls:
        return _THE_REAL_OPEN(self, *args, **kwargs)
    call = calls[-1]
    if call.entry_pending:
        call.entry_pending = False
        return _THE_REAL_OPEN(self, *args, **kwargs)
    target = args[0] if args else kwargs.get("fullurl")
    arguments = {"url": _rendered(target)}
    with call.boundary.request(call.capability, arguments) as handle:
        response = _THE_REAL_OPEN(self, *args, **kwargs)
        status = getattr(response, "status", None)
        if status is not None:
            handle.record_outcome(_status_digest(status))
        return response


def _rendered(value):
    """`url` as the digest sees it: a `Request`'s own address, or text of whatever else."""
    if hasattr(value, "full_url"):
        return value.full_url
    return str(value)


def _status_digest(status):
    """`sha256("status:" + str(status))`: the outcome recorded for a request let through.

    Handed to the boundary's outcome log, which `instrument run` does not give
    one — its boundary discards outcomes. The manifest declares no member for
    them; a caller that builds a boundary with a log of its own receives this.
    """
    return hashlib.sha256(f"status:{status}".encode()).hexdigest()
