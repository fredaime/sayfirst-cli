# SPDX-License-Identifier: Apache-2.0
"""The interposition engine: it installs what a pack declares, and knows no library.

Layer 1 of the instrumentation chain. It reads no policy, holds no cache and
learns nothing about why a decision came back as it did: it puts the boundary's
one shape in front of a named attribute and gets out of the way. A program can
use the boundary by hand with no engine at all, and that is a supported way to
use it rather than a workaround.

Two installation paths, because a process has exactly two states for any given
module. One already in the interpreter is replaced where it sits. One not yet
loaded is replaced by a single entry at the head of the import path, which asks
the entries behind it for the real answer and wraps only the loader — so the
module is found, built and executed exactly as it would have been, and the
declared attributes are replaced after its body has run. That is also why
`from … import …` receives the replacement: the name is bound after the module
is complete.

**The hole this mechanism has, stated rather than hidden.** A program that bound
a reference before this ran, or that was started by anything other than the
launcher, is not instrumented. Nothing here detects that, and nothing here
reports coverage it did not have — finding that gap is the verifier's job, and
the two deliberately share no bookkeeping, because a proof that trusts the thing
it is proving is not a proof.

**All or nothing, and one installation per engine.** Every point is resolved and
every replacement made before the first attribute is replaced, so an install
that refuses leaves the process exactly as it found it — a half-installed set of
points is a program running partly governed with nothing saying which part. And
an engine installs once: a second install would leave a point still waiting for
its module to be wrapped with a boundary and a scope it was not installed with.

**One refusal surfaces after the hand-off, and it cannot surface sooner.** A
point naming an attribute of a module that is not loaded yet cannot be checked
until that module has run: the attribute does not exist to be absent. So that
one arrives as `EngineMisuse` out of the program's own import, where the
launcher no longer rewrites anything (`launch.py` says why). Every other refusal
is found before the program starts.

Reversible by construction, which is what article 9 asks of the primary mode:
nothing is written anywhere — the pack's own directory included, whose
execution module is loaded through a loader with the bytecode write taken out
(`_NoBytecode` says how) — and `uninstall` puts back the very objects that were
taken away, not equal ones.

**This file names no library, and a guard walks its source to say so.** Not as
an identifier, not in a string, not in a docstring. An engine is exactly where
a special case for a popular library is cheapest to add and hardest to see, so
the rule is mechanical rather than remembered.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from importlib.machinery import ModuleSpec, SourceFileLoader
from types import ModuleType
from typing import Protocol

from .manifest import Pack, Point


class EngineMisuse(RuntimeError):
    """The engine was asked for something it must refuse, and says which and why."""


class Wrapper(Protocol):
    """What a pack's execution module provides: the replacement for one attribute."""

    def __call__(self, original: object, capability: str, boundary: object) -> object: ...


class Asking(Protocol):
    """The whole of what the engine needs from a boundary, and no more of it."""

    def request(
        self, capability: str, arguments: Mapping[str, object], *, scope: str
    ) -> object: ...


class _InScope:
    """The boundary, with the scope this installation was made in already supplied.

    The seam is « the engine calls only `request(capability, arguments)` and the
    handle's `record_outcome` », and the call itself is made by a pack's wrapper.
    The scope is not the pack's to know and not the pack's to choose — it is the
    invocation's, named on the command line — so the engine binds it here rather
    than widening the signature every pack implements. What a pack is handed is
    still a thing with `request` and nothing else, called with a capability and
    arguments, which is the seam unchanged.

    Nothing else is forwarded. A pack that tried to choose a scope of its own
    would find no parameter to choose it with, which is the point.
    """

    def __init__(self, boundary: Asking, scope: str) -> None:
        self._boundary = boundary
        self._scope = scope

    def request(self, capability: str, arguments: Mapping[str, object]) -> object:
        """Ask in the scope the invocation named, about what the pack declared."""
        return self._boundary.request(capability, arguments, scope=self._scope)


class Engine:
    """One installation, plus the record needed to take it back exactly."""

    def __init__(self) -> None:
        self._taken: list[tuple[ModuleType, str, object]] = []
        self._awaited: dict[str, list[tuple[Point, Wrapper]]] = {}
        self._boundary: _InScope | None = None
        self._finder: _Finder | None = None
        self._installed = False

    def install(self, packs: Sequence[Pack], boundary: Asking, *, scope: str) -> None:
        """Put the boundary in front of every point every pack declares.

        Each pack's execution module is loaded first, so a pack that cannot
        produce a wrapper is refused before anything at all is replaced: a
        half-installed set of points is a program running partly governed with
        nothing saying which part.

        `scope` is required and has no default. An engine that picked one would
        be choosing where a question is asked, which is the invocation's to
        choose and nobody else's — and a default that quietly matched the
        contract's would make a scope somebody typed indistinguishable from a
        scope nobody did.
        """
        if self._installed:
            raise EngineMisuse(
                "this engine is already installed; uninstall first. One installation per "
                "engine, because a point still waiting for its module would otherwise be "
                "wrapped with a boundary and a scope it was not installed with"
            )
        arriving = _planned(packs)
        asking = _InScope(boundary, scope)
        # Resolved and made in full before the first attribute is replaced, so an
        # install that refuses leaves this process exactly as it found it.
        prepared: list[tuple[ModuleType, Point, object, object]] = []
        for name in sorted(arriving):
            if name not in sys.modules:
                continue
            loaded = sys.modules[name]
            for point, wrapper in arriving[name]:
                original = _original_of(loaded, point)
                prepared.append((loaded, point, original, _made(wrapper, original, point, asking)))
        self._boundary = asking
        for loaded, point, original, replacement in prepared:
            setattr(loaded, point.attribute, replacement)
            self._taken.append((loaded, point.attribute, original))
        for name in sorted(arriving):
            if name not in sys.modules:
                self._awaited[name] = list(arriving[name])
        if self._awaited:
            self._finder = _Finder(self)
            sys.meta_path.insert(0, self._finder)
        self._installed = True

    def uninstall(self) -> None:
        """Give every original back, and take the entry out of the import path.

        Idempotent, and ordered last-first, so a point wrapped over another
        engine's work restores the object that engine had left in place.
        """
        while self._taken:
            loaded, attribute, original = self._taken.pop()
            setattr(loaded, attribute, original)
        if self._finder is not None and self._finder in sys.meta_path:
            sys.meta_path.remove(self._finder)
        self._finder = None
        self._awaited.clear()
        self._boundary = None
        self._installed = False

    def _replace(self, loaded: ModuleType, point: Point, wrapper: Wrapper) -> None:
        """Replace one attribute of a module that has just finished loading.

        The one path that can refuse after the program has started, because the
        attribute did not exist to be absent until now.
        """
        original = _original_of(loaded, point)
        setattr(loaded, point.attribute, _made(wrapper, original, point, self._boundary))
        self._taken.append((loaded, point.attribute, original))

    def _awaiting(self, name: str) -> bool:
        """Whether any point is waiting for this module to be loaded."""
        return name in self._awaited

    def _arrived(self, name: str, loaded: ModuleType) -> None:
        """Called by the wrapped loader, once, after the module's own body has run."""
        for point, wrapper in self._awaited.pop(name, []):
            self._replace(loaded, point, wrapper)


class _Finder:
    """One entry at the head of the import path, for the modules a pack awaits.

    It finds nothing itself. It asks the entries behind it for the real answer
    and replaces the loader on it, so a module is located and executed by
    whatever would have located and executed it — a finder of its own would be
    this engine deciding how somebody's code is loaded, which is not its
    business and would break the moment that code is packaged differently.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._asking: set[str] = set()

    def find_spec(
        self, fullname: str, path: object = None, target: ModuleType | None = None
    ) -> ModuleSpec | None:
        if not self._engine._awaiting(fullname) or fullname in self._asking:
            # Re-entrant because the entries behind may import on the way to an
            # answer; answering `None` there lets the real answer through.
            return None
        self._asking.add(fullname)
        try:
            found = _spec_from_the_others(self, fullname, path, target)
        finally:
            self._asking.discard(fullname)
        if found is None or found.loader is None:
            return None
        found.loader = _Loader(found.loader, self._engine, fullname)
        return found


class _Loader:
    """The real loader, with the pack's replacements applied after the body has run."""

    def __init__(self, original: object, engine: Engine, fullname: str) -> None:
        self._original = original
        self._engine = engine
        self._fullname = fullname

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        make = getattr(self._original, "create_module", None)
        return None if make is None else make(spec)

    def exec_module(self, module: ModuleType) -> None:
        self._original.exec_module(module)  # type: ignore[attr-defined]
        self._engine._arrived(self._fullname, module)

    def __getattr__(self, name: str) -> object:
        """Everything else the import system may ask, answered by the real loader."""
        return getattr(self._original, name)


def _spec_from_the_others(
    mine: _Finder, fullname: str, path: object, target: ModuleType | None
) -> ModuleSpec | None:
    """Ask every other entry of the import path, in order, as the interpreter would."""
    for entry in list(sys.meta_path):
        if entry is mine:
            continue
        ask = getattr(entry, "find_spec", None)
        if ask is None:
            continue
        found = ask(fullname, path, target)
        if found is not None:
            return found
    return None


class _NoBytecode(SourceFileLoader):
    """The interpreter's own source loader, with the bytecode write taken out.

    One method writes that cache, and this is it. `SourceLoader.get_code`
    compiles the source and hands the result to `_cache_bytecode`, which
    `SourceFileLoader` adapts to `set_data` — and `get_code` treats a
    `NotImplementedError` from it as a loader that does not cache, which is the
    import system's own way of saying so. Overriding `set_data` to write
    nothing therefore removes the write instead of moving it: there is no other
    route from a load to a file. The spec's `cached` is not that route — the
    path written is computed from the source path, not from the spec — which is
    why it is not what this uses.

    Why the engine bothers: a pack is a directory somebody else owns, and may
    be one nothing may be written into — a system path, a container layer, a
    signed bundle. This file claims the primary mode writes nothing anywhere,
    and a pack's own directory is somewhere.
    """

    def set_data(self, path: str, data: bytes, *, _mode: int = 0o666) -> None:
        """Write nothing: the one method a source loader writes its cache through."""

    def get_code(self, fullname: str) -> object:
        """Compile the source, always: a cache found beside it is never read.

        The ordinary loader prefers a bytecode file whose recorded size and
        mtime match the source, so a `.pyc` planted beside `interpose.py`
        would run in place of the file `sayfirst packs check` read and a person
        audited. The execution module is the audited text and nothing else.
        """
        path = self.get_filename(fullname)
        return self.source_to_code(self.get_data(path), path)


def _wrapper_of(pack: Pack) -> Wrapper:
    """Load the pack's own execution module by path, and take its `wrap`.

    By path and never by name: a pack is a directory a person named on the
    command line, not a distribution on the import path, and resolving one from
    a name is a registry wearing another hat (article 9).

    Through `_NoBytecode`, so the load leaves the pack's directory exactly as it
    was found.
    """
    location = pack.execution_module
    name = f"sayfirst_pack_{pack.name}"
    spec = importlib.util.spec_from_file_location(
        name, location, loader=_NoBytecode(name, str(location))
    )
    if spec is None or spec.loader is None:
        # Not reachable while the loader is supplied above, and kept: the
        # published contract of `spec_from_file_location` is « a spec or
        # nothing », and an engine that read attributes off `None` would answer
        # a pack's problem with a traceback of its own. A file that is not a
        # module this interpreter can load arrives below instead, out of
        # `exec_module`, as the pack's failure said as one.
        raise EngineMisuse(f"{location} is not a module this interpreter can load")
    loaded = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(loaded)
    except Exception as failed:
        # A pack is code the person running it chose, exactly like a dependency,
        # so a pack that will not load is their pack to fix — never an answer
        # about their program, and never a traceback out of this engine.
        raise EngineMisuse(f"{location} did not load: {failed!r}") from failed
    made = getattr(loaded, "wrap", None)
    if not callable(made):
        raise EngineMisuse(
            f"{location} declares no callable wrap: the execution module's whole job is "
            f"to produce the replacement, given the original attribute, the capability "
            f"and the boundary"
        )
    return made


def _made(wrapper: Wrapper, original: object, point: Point, boundary: object) -> object:
    """The replacement the pack produces, or the pack's own failure said as one.

    A wrapper factory that raises has not produced a wrapper, so there is
    nothing to install and nothing was installed. Whatever it raised is carried
    in the sentence rather than out of the engine, because the caller has to be
    able to tell « your pack is wrong » from « the control plane said no ».
    """
    try:
        return wrapper(original, point.capability, boundary)
    except EngineMisuse:
        raise
    except Exception as failed:
        raise EngineMisuse(
            f"the wrapper for {point.attribute} of {point.module} could not be made: {failed!r}"
        ) from failed


def _planned(packs: Sequence[Pack]) -> dict[str, list[tuple[Point, Wrapper]]]:
    """Every point every pack declares, by module, refusing a point claimed twice.

    The execution modules are loaded here, which is the earliest anything can
    refuse: a pack that will not load, or that produces no wrapper, is found
    before a single attribute has been looked up.
    """
    arriving: dict[str, list[tuple[Point, Wrapper]]] = {}
    claimed: set[tuple[str, str]] = set()
    for pack in packs:
        wrapper = _wrapper_of(pack)
        for point in pack.points:
            claim = (point.module, point.attribute)
            if claim in claimed:
                raise EngineMisuse(
                    f"{point.attribute} of {point.module} is already wrapped: a second "
                    f"wrapper around the first would ask twice for one effect, and "
                    f"nothing afterwards could say which pack a caller meant"
                )
            claimed.add(claim)
            arriving.setdefault(point.module, []).append((point, wrapper))
    return arriving


def _original_of(loaded: ModuleType, point: Point) -> object:
    """The attribute a point names, or the refusal that it is not there.

    The engine wraps what a pack names and invents nothing, so a point naming an
    absent attribute is refused rather than passed over in silence (article 2):
    a pack that appears to govern an effect it never wrapped is exactly the false
    all-clear this chain exists to prevent.
    """
    if not hasattr(loaded, point.attribute):
        raise EngineMisuse(
            f"{point.module} has no {point.attribute}: the engine wraps what a pack "
            f"names and invents nothing, so a point naming an absent attribute is "
            f"refused rather than passed over in silence (article 2)"
        )
    return getattr(loaded, point.attribute)
