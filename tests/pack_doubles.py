# SPDX-License-Identifier: Apache-2.0
"""The doubles the three shipped-pack suites drive their packs against, spelled once.

Each of `tests/test_subprocess_pack.py`, `tests/test_http_client_pack.py` and
`tests/test_database_pack.py` carried its own copy of every double below, and
two of them — `Handle` and `FakeBoundary` — were identical by AST hash across
all three. So a correction to either had to be made three times, and a run in
which it was made twice was green: the suite that still held the old double
tested the old double, and nothing anywhere said so. That is what the
duplication cost, and it is the reason this file exists rather than a preference
about tidiness.

**The other four were NOT identical, and the differences were real.** `Spy`
guarded `inspect.signature` in one file and not in the other two, because one of
the three originals has no signature this interpreter can parse.
`RefusingBoundary` carried the full reasoning in one file and a pointer to it in
the others. `governed_by` replaces a different attribute of a different module
in each. The two fixtures differ in the pack they install and in the sentence
that says which import path that pack's module reaches it on. So this file holds
the UNION rather than one of the three copies: the guarded signature (the
behaviour of the only copy that had to have it, and identical for the two that
did not), the full reasoning, and the parts that differ passed in as arguments.

What stays in each suite is what is genuinely that pack's: its `PACK`, the call
shapes it governs, the capability its refusals name, and the fixture sentence
about its own module. `tests/test_pack_doubles.py` holds the rule that no suite
defines one of these classes again.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path
from types import ModuleType

from sayfirst_cli.instrument import manifest
from sayfirst_cli.instrument.engine import Engine


class Handle:
    """What the body may say about what it did, and nothing else."""

    def __init__(self) -> None:
        self.recorded: list[str] = []

    def record_outcome(self, digest: str) -> None:
        self.recorded.append(digest)


class FakeBoundary:
    """The whole of what the engine may use: `request`, and the handle it yields."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, Mapping[str, object]]] = []
        self.handles: list[Handle] = []

    @contextmanager
    def request(
        self, capability: str, arguments: Mapping[str, object], *, scope: str = "local"
    ) -> Iterator[Handle]:
        self.asked.append((capability, dict(arguments)))
        handle = Handle()
        self.handles.append(handle)
        yield handle


class RefusingBoundary:
    """A boundary that refuses, in the shape the real one refuses in.

    `sayfirst_boundary.Boundary.request` is a generator context manager that
    puts the question BEFORE it yields and raises the outcome out of the ask
    itself — see its `_ask`, which raises `Denied`, `Suspended`, `AskRefused`
    or `CouldNotAsk` before any grant exists. So every refusal reaches a pack's
    wrapper the same way: as an exception out of `__enter__`, with the body of
    the `with` never entered. This double does exactly that and nothing else.
    """

    def __init__(self, refusal: BaseException) -> None:
        self.refusal = refusal
        self.asked: list[tuple[str, Mapping[str, object]]] = []

    @contextmanager
    def request(
        self, capability: str, arguments: Mapping[str, object], *, scope: str = "local"
    ) -> Iterator[None]:
        self.asked.append((capability, dict(arguments)))
        raise self.refusal
        # Never reached, and not removable: a `yield` is what makes this a
        # generator, which is what makes the refusal arrive out of `__enter__`
        # rather than out of the call that builds the context manager.
        yield None


class Spy:
    """The original, recorded: what it was called with, and whether it was at all.

    Stands in for the real attribute so that « the original was not called » is
    a recorded fact rather than an inference from an effect that did or did not
    appear. It delegates to what it stands in for, so every path where the
    effect is allowed to happen behaves exactly as it would have.
    """

    def __init__(self, original: object) -> None:
        self.original = original
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        #: `interpose.wrap` reads the signature of whatever it wraps, and binds
        #: each call against it to find the arguments a manifest names. A
        #: stand-in reporting its own `(*args, **kwargs)` would change the thing
        #: being measured, so it reports the signature of what it stands in for.
        #:
        #: Best-effort, because one of the three originals has no signature
        #: `inspect` can parse (`interpose.py`'s own docstring says why); the
        #: wrapper for that one reads its argument positionally and does not
        #: depend on this. For the other two the guard never fires, so it is the
        #: union of the three copies this replaces rather than a relaxation.
        with suppress(TypeError, ValueError):
            self.__signature__ = inspect.signature(original)

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return self.original(*args, **kwargs)  # type: ignore[operator]


def engine_fixture() -> Iterator[Engine]:
    """One engine, always uninstalled, so no test leaves its pack's attribute wrapped.

    A generator rather than a fixture, so each suite declares the fixture in its
    own file — naming the attribute it is protecting — while the body that has
    to be right is here once.
    """
    made = Engine()
    try:
        yield made
    finally:
        made.uninstall()
    assert not [
        finder for finder in sys.meta_path if type(finder).__module__.startswith("sayfirst_cli")
    ]


def installed(engine: Engine, pack: Path) -> FakeBoundary:
    """One pack installed on a granting boundary, and the boundary to read it off."""
    boundary = FakeBoundary()
    engine.install([manifest.read_pack(pack)], boundary, scope="local")
    return boundary


@contextmanager
def governed_by(
    boundary: object,
    *,
    pack: Path,
    holder: ModuleType,
    attribute: str,
    original: object,
) -> Iterator[Spy]:
    """The shipped pack installed over a recording stand-in for the real attribute.

    The stand-in is put in place BEFORE the engine installs, so the pack wraps
    it exactly as it wraps the real attribute. Everything is put back here
    rather than in a fixture, in the reverse order it was taken: a fixture
    restoring the attribute could be finalised before the engine's own
    uninstall, which would put the stand-in back and leave it there.
    """
    spy = Spy(original)
    engine = Engine()
    setattr(holder, attribute, spy)
    try:
        engine.install([manifest.read_pack(pack)], boundary, scope="local")
        try:
            yield spy
        finally:
            engine.uninstall()
    finally:
        setattr(holder, attribute, original)
