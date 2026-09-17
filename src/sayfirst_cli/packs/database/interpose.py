# SPDX-License-Identifier: Apache-2.0
"""Ask before a database is opened. There is nothing afterwards to record.

Governs the one attribute this pack's point names: the call this module's
`[[point]]` wraps opens a database and hands back a connection, and that call
is the whole of what this pack governs.

`database` — the database the call is asked to open, rendered as the text it
names whatever shape the caller passed it in — is the one argument sent to the
boundary. Nothing else of the call is sent (article 11: what is sent is a
digest, and which arguments it covers is declared, never implicit).

**As text, whatever the caller's type — the same rule `subprocess`'s pack
already keeps.** `sqlite3.connect` accepts a plain `str` — a file path, or the
special name for an in-memory database — a `bytes` path, or an
`os.PathLike`; all three name one database. Each is decoded to the text it
names with `os.fsdecode` (the interpreter's own path decoding, and the exact
function the sibling `subprocess` pack uses for its own `args`) before the
digest is taken, so `sqlite3.connect("/x/db")` and
`sqlite3.connect(b"/x/db")` — two spellings that open the same file — arrive
at the boundary under one digest. Rendering the `bytes` shape with `str()`
instead would send its `repr` (`"b'/x/db'"`), which is a second, unrelated
digest for the same database and a policy keyed on `database` could be stepped
around by spelling the path in bytes — exactly the defect class `subprocess`'s
own docstring already names for its own argument.

**Bound by position, not by `inspect.signature`.** `subprocess`'s pack and this
distribution's `http-client` pack both bind the call against
`inspect.signature(original)`, because `subprocess.Popen` and
`urllib.request.urlopen` both support it. The real `sqlite3.connect` does not:
its C implementation's own printed signature carries a default —
`autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL` — that is not a Python literal,
so `inspect.signature(sqlite3.connect)` raises on the very interpreter this
pack ships for. That is a fact about the standard library's own C
implementation on this Python version, not something fixable from outside it.
`database` is the DB-API 2.0 shape's first parameter — the rule every driver's
`connect` follows, this one included — so it is read from the keyword if the
caller used one and from the first positional argument otherwise: exactly what
`inspect.signature(...).bind_partial(...)` would have read, had it been able
to run at all.

**No outcome digest.** A connection is not an outcome: unlike a spawned
process, which has a pid the moment it exists, or a finished HTTP exchange,
which has a status, a connection that has just been opened has nothing yet
worth digesting, and a failed open never reaches the line that would record
one — the exception propagates out of the call itself, before the ask's `with`
block would have anything to say. So this pack's point declares no outcome
digest, and none is recorded here.

The wrapper is a plain function, so what it returns is the real connection
object, never a stand-in for it.
"""

from __future__ import annotations

import os


def wrap(original, capability, boundary):
    """Ask, open, and hand back the connection. See the module docstring for
    why `database` is read positionally rather than through `inspect.signature`."""

    def wrapper(*args, **kwargs):
        database = kwargs.get("database", args[0] if args else None)
        arguments = {"database": _rendered(database)}
        with boundary.request(capability, arguments):
            return original(*args, **kwargs)

    return wrapper


def _rendered(value):
    """`database` as the digest sees it: text, whatever the caller spelled it in.

    `bytearray` is converted to `bytes` first because `os.fsdecode` does not
    accept it directly (it takes `str`, `bytes` and `os.PathLike`), not because
    `sqlite3.connect` is known to accept a `bytearray` database — the rendering
    is defined for whatever `original` is actually called with, the same way
    `subprocess`'s own `_text` is.
    """
    if isinstance(value, bytearray):
        value = bytes(value)
    if isinstance(value, str | bytes | os.PathLike):
        return os.fsdecode(value)
    return str(value)
