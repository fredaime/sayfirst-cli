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
"""

from __future__ import annotations

import hashlib
import inspect


def wrap(original, capability, boundary):
    """Bind the call to `original`'s own signature, ask, open, and record the status.

    The ask carries `url` rendered as text — a `Request`'s own address, or
    `str()` of whatever else was passed — so the digest is computable
    whichever shape the caller called with.
    """
    signature = inspect.signature(original)

    def wrapper(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        arguments = {"url": _rendered(bound.arguments.get("url"))}
        with boundary.request(capability, arguments) as handle:
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


def _rendered(value):
    """`url` as the digest sees it: a `Request`'s own address, or text of whatever else."""
    if hasattr(value, "full_url"):
        return value.full_url
    return str(value)


def _status_digest(status):
    """`sha256("status:" + str(status))`, as the manifest's `audit_event` expects to see it."""
    return hashlib.sha256(f"status:{status}".encode()).hexdigest()
