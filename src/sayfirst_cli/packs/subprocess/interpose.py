# SPDX-License-Identifier: Apache-2.0
"""Ask before a process is spawned, and record which one answered.

Governs `subprocess.Popen` — the one attribute this pack's point names. It
governs `subprocess.run`, `subprocess.call` and `subprocess.check_output` too,
without a point of their own, because all three call the module's own global
`Popen` to do their spawning: wrapping the name they call is wrapping them,
and a second point for `run` would be asking about one spawn twice.

`args` — a command line as text, or the sequence `Popen` accepts rendered as a
list of text; anything else (there should be none: `Popen`'s first argument is
required) is rendered with `str()`, so the digest `pack.toml` declares
(`digest = ["args"]`) is always computable — is the one argument sent to the
boundary. Nothing else of the call is sent (article 11: what is sent is a
digest, and which arguments it covers is declared, never implicit).

**As text, whatever the caller's type.** `Popen` accepts a command line as
`str`, as `bytes`, as a `os.PathLike`, or as a sequence of any of those, and
they all spawn the same process. So each is decoded to the text it names
(`os.fsdecode`, the interpreter's own path decoding) before the digest is
taken: two calls that spawn one process have one digest, and a policy keyed on
the command line — which is all `digest = ["args"]` gives the plane — cannot be
stepped around by spelling the same command in bytes.

The wrapper is a plain function, not a class, so `subprocess.run`'s own
`with Popen(...) as process:` still works: what this returns is the real
`Popen` instance, never a stand-in for it.
"""

from __future__ import annotations

import hashlib
import inspect
import os
from collections.abc import Sequence


def wrap(original, capability, boundary):
    """Bind the call to `original`'s own signature, ask, spawn, and record the pid.

    The ask carries the command line as text — a `bytes` command line is
    decoded rather than digested as bytes — so the same spawn has the same
    digest whatever type the caller spelled it in.
    """
    signature = inspect.signature(original)

    def wrapper(*args, **kwargs):
        bound = signature.bind_partial(*args, **kwargs)
        arguments = {"args": _rendered(bound.arguments.get("args"))}
        with boundary.request(capability, arguments) as handle:
            process = original(*args, **kwargs)
            if hasattr(process, "pid"):
                # A process that has just been spawned has a pid and nothing
                # else to report yet; that is the whole of the outcome here.
                handle.record_outcome(_pid_digest(process.pid))
            return process

    return wrapper


def _rendered(value):
    """`args` as the digest sees it: text, a list of text, or `str()` of whatever else.

    The one command line a caller may spell four ways — `str`, `bytes`,
    `bytearray`, `os.PathLike` — is one command line, and `bytes` is decoded
    before the sequence branch is even considered: it IS a sequence, of
    integers, and rendering it as one would send the plane a list of byte codes
    for a command a second caller sends as a string.
    """
    if isinstance(value, str | bytes | bytearray | os.PathLike):
        return _text(value)
    if isinstance(value, Sequence):
        return [_text(item) for item in value]
    return str(value)


def _text(value):
    """One command line, or one element of one, as the text it names."""
    if isinstance(value, bytearray):
        # `os.fsdecode` takes `str`, `bytes` and `os.PathLike`, and a
        # `bytearray` is none of the three.
        value = bytes(value)
    if isinstance(value, str | bytes | os.PathLike):
        return os.fsdecode(value)
    return str(value)


def _pid_digest(pid):
    """`sha256("pid:" + str(pid))`, as the manifest's `audit_event` expects to see it."""
    return hashlib.sha256(f"pid:{pid}".encode()).hexdigest()
