# SPDX-License-Identifier: Apache-2.0
"""The interposition engine, proven on a module written for this test alone.

Not one assertion here touches a real library. The module being wrapped is
written into a temporary directory and put on the path for the length of one
test, because a guard that reached for a convenient standard-library name would
be teaching the engine a vocabulary the whole design says it must not have —
and `tests/test_engine_is_agnostic.py` would then be checking a rule this file
had already broken.

The boundary is a double exposing the one shape the seam permits: `request` as a
context manager, yielding something with `record_outcome`. If the engine ever
needs more than that from a boundary, this file stops compiling, which is the
point of writing the double by hand rather than reaching for a mock.
"""

from __future__ import annotations

import importlib
import itertools
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from sayfirst_cli.instrument import manifest
from sayfirst_cli.instrument.engine import Engine, EngineMisuse

#: A module of no consequence: one function, one value, and nothing imported.
TARGET_MODULE = '''\
VALUE = "original"


def effect(first, second=2):
    """Return something recognisable, so a wrapper cannot fake having called it."""
    return ("effect", first, second)
'''

#: An execution module in the shape the seam names: `wrap(original, capability,
#: boundary)` produces the replacement, and the replacement asks before it acts.
INTERPOSE = '''\
# SPDX-License-Identifier: Apache-2.0
"""A wrapper that asks with the capability it was given, then calls the original."""

ASKED = []


def wrap(original, capability, boundary):
    def wrapper(*args, **kwargs):
        arguments = {"first": args[0] if args else kwargs.get("first")}
        ASKED.append((capability, arguments))
        with boundary.request(capability, arguments) as grant:
            result = original(*args, **kwargs)
            grant.record_outcome("sha256:" + "0" * 64)
            return result

    wrapper.wrapped_by_the_pack = True
    return wrapper
'''


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
        self.scopes: list[str] = []
        self.handles: list[Handle] = []

    @contextmanager
    def request(
        self, capability: str, arguments: Mapping[str, object], *, scope: str = "local"
    ) -> Iterator[Handle]:
        self.asked.append((capability, dict(arguments)))
        self.scopes.append(scope)
        handle = Handle()
        self.handles.append(handle)
        yield handle


def plant_pack(root: Path, *, module: str, attribute: str, capability: str, name: str) -> Path:
    """A pack directory of this test's own, complete and valid."""
    directory = root / name
    directory.mkdir()
    (directory / manifest.MANIFEST_FILE).write_text(
        "[pack]\n"
        f'name = "{name}"\n'
        'classification = "convenience"\n'
        "classified_on = 2026-09-14\n"
        "\n"
        "[[point]]\n"
        f'module = "{module}"\n'
        f'attribute = "{attribute}"\n'
        f'capability = "{capability}"\n'
        'digest = ["first"]\n'
        f'audit_event = "{module}.{attribute}"\n',
        encoding="utf-8",
    )
    (directory / manifest.EXECUTION_MODULE).write_text(INTERPOSE, encoding="utf-8")
    (directory / manifest.CLASSIFICATION_NOTE).write_text(
        "A convenience pack written for one test.\n", encoding="utf-8"
    )
    return directory


_names = itertools.count()


@pytest.fixture
def target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A throwaway module on the path, removed from the interpreter afterwards."""
    made: list[str] = []
    monkeypatch.syspath_prepend(str(tmp_path))

    def write(body: str = TARGET_MODULE) -> str:
        name = f"sayfirst_target_{next(_names)}"
        (tmp_path / f"{name}.py").write_text(body, encoding="utf-8")
        importlib.invalidate_caches()
        made.append(name)
        return name

    yield write
    for name in made:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def engine() -> Iterator[Engine]:
    """One engine, always uninstalled, so no test can leave a finder behind."""
    made = Engine()
    try:
        yield made
    finally:
        made.uninstall()
    assert not [
        finder for finder in sys.meta_path if type(finder).__module__.startswith("sayfirst_cli")
    ]


def pack_for(tmp_path: Path, module: str, *, capability: str = "example.action") -> Any:
    name = f"pack-{next(_names)}"
    return manifest.read_pack(
        plant_pack(tmp_path, module=module, attribute="effect", capability=capability, name=name)
    )


def test_a_module_imported_after_install_is_wrapped(tmp_path: Path, target, engine: Engine) -> None:
    """The finder's whole purpose: the program's own import arrives instrumented."""
    name = target()
    boundary = FakeBoundary()
    engine.install([pack_for(tmp_path, name)], boundary, scope="local")
    loaded = importlib.import_module(name)
    assert getattr(loaded.effect, "wrapped_by_the_pack", False) is True
    assert loaded.effect(1, 2) == ("effect", 1, 2)
    assert boundary.asked == [("example.action", {"first": 1})]
    assert boundary.handles[0].recorded == ["sha256:" + "0" * 64]


def test_the_wrapper_asks_with_the_capability_the_pack_declared(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The manifest's vocabulary is the interface; the engine invents no capability."""
    name = target()
    boundary = FakeBoundary()
    engine.install([pack_for(tmp_path, name, capability="process.spawn")], boundary, scope="local")
    importlib.import_module(name).effect(7)
    assert [capability for capability, _ in boundary.asked] == ["process.spawn"]


def test_a_module_imported_before_install_is_wrapped_in_place(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The other half of the mechanism: a module already in the interpreter."""
    name = target()
    loaded = importlib.import_module(name)
    original = loaded.effect
    boundary = FakeBoundary()
    engine.install([pack_for(tmp_path, name)], boundary, scope="local")
    assert loaded.effect is not original
    assert loaded.effect(3) == ("effect", 3, 2)
    assert boundary.asked == [("example.action", {"first": 3})]


def test_from_module_import_attribute_yields_the_wrapper(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The binding a program actually writes, which happens after the module ran."""
    name = target()
    boundary = FakeBoundary()
    engine.install([pack_for(tmp_path, name)], boundary, scope="local")
    namespace: dict[str, object] = {}
    exec(f"from {name} import effect", namespace)  # the binding under test
    taken = namespace["effect"]
    assert getattr(taken, "wrapped_by_the_pack", False) is True
    assert taken(5) == ("effect", 5, 2)
    assert boundary.asked == [("example.action", {"first": 5})]


def test_loading_a_pack_writes_nothing_into_its_directory(
    tmp_path: Path, target, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`engine.py`'s « nothing is written anywhere » covers the pack's own tree.

    Loading an execution module the ordinary way writes a bytecode cache beside
    it — a file in a directory this client does not own and may not be allowed
    to write into at all. Held on the directory's entries rather than on the
    absence of one name: whatever a load would have written, it is not there.
    """
    # Pinned, so a host that sets PYTHONDONTWRITEBYTECODE cannot make this
    # test pass for a loader that would have written.
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    name = target()
    directory = plant_pack(
        tmp_path, module=name, attribute="effect", capability="example.action", name="uncached"
    )
    before = sorted(item.name for item in directory.iterdir())
    assert before == sorted(manifest.REQUIRED_FILES), before
    engine.install([manifest.read_pack(directory)], FakeBoundary(), scope="local")
    # The execution module really ran: the wrapper now in place came from it.
    loaded = importlib.import_module(name)
    assert getattr(loaded.effect, "wrapped_by_the_pack", False) is True
    assert sorted(item.name for item in directory.iterdir()) == before


def test_uninstall_gives_back_the_original_object(tmp_path: Path, target, engine: Engine) -> None:
    """Reversible means the very object that was taken away, not an equal one."""
    name = target()
    loaded = importlib.import_module(name)
    original = loaded.effect
    engine.install([pack_for(tmp_path, name)], FakeBoundary(), scope="local")
    assert loaded.effect is not original
    engine.uninstall()
    assert loaded.effect is original
    assert loaded.effect(4) == ("effect", 4, 2)


def test_uninstall_removes_the_finder_installed_for_a_module_not_yet_imported(
    tmp_path: Path, target, engine: Engine
) -> None:
    """A finder left in the import path would outlive the engine that put it there."""
    name = target()
    before = list(sys.meta_path)
    engine.install([pack_for(tmp_path, name)], FakeBoundary(), scope="local")
    assert sys.meta_path != before
    engine.uninstall()
    assert sys.meta_path == before


def test_a_second_install_on_one_engine_is_refused(tmp_path: Path, target, engine: Engine) -> None:
    """A point still awaiting its module would be wrapped with the wrong boundary.

    Measured before this rule: `install` on `probe_m1` with one boundary and
    then on `probe_m2` with another, and importing `probe_m1` afterwards gave a
    wrapper holding the SECOND boundary — a program's questions going through a
    boundary the engine was not installed with.
    """
    name = target()
    engine.install([pack_for(tmp_path, name)], FakeBoundary(), scope="local")
    with pytest.raises(EngineMisuse) as raised:
        engine.install([pack_for(tmp_path, target())], FakeBoundary(), scope="local")
    assert "already installed" in str(raised.value)
    assert "uninstall" in str(raised.value)


def test_the_awaited_point_keeps_the_boundary_it_was_installed_with(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The probe the review ran, now that the second install cannot happen."""
    first_name, second_name = target(), target()
    first = FakeBoundary()
    engine.install([pack_for(tmp_path, first_name)], first, scope="first-scope")
    with pytest.raises(EngineMisuse):
        engine.install([pack_for(tmp_path, second_name)], FakeBoundary(), scope="second-scope")
    importlib.import_module(first_name).effect(1)
    assert first.scopes == ["first-scope"]
    assert first.asked == [("example.action", {"first": 1})]


def test_an_engine_can_be_installed_again_after_it_is_uninstalled(
    tmp_path: Path, target, engine: Engine
) -> None:
    """« Uninstall first » is an instruction, so it has to work."""
    name = target()
    engine.install([pack_for(tmp_path, name)], FakeBoundary(), scope="local")
    engine.uninstall()
    second = FakeBoundary()
    engine.install([pack_for(tmp_path, name)], second, scope="second-scope")
    importlib.import_module(name).effect(2)
    assert second.scopes == ["second-scope"]


def test_two_packs_declaring_the_same_point_are_refused_in_one_install(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The same refusal when the collision is between two packs of one invocation."""
    name = target()
    packs = [pack_for(tmp_path, name), pack_for(tmp_path, name)]
    with pytest.raises(EngineMisuse):
        engine.install(packs, FakeBoundary(), scope="local")


def test_a_point_naming_an_attribute_the_module_has_not_got_is_refused(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The engine wraps what a pack names and invents nothing to wrap."""
    name = target("VALUE = 1\n")
    importlib.import_module(name)
    with pytest.raises(EngineMisuse) as raised:
        engine.install([pack_for(tmp_path, name)], FakeBoundary(), scope="local")
    assert "effect" in str(raised.value)


def test_an_execution_module_without_a_wrap_is_refused(tmp_path: Path, engine: Engine) -> None:
    """The pack's one obligation, checked before anything is installed."""
    directory = plant_pack(
        tmp_path,
        module="sayfirst_absent_target",
        attribute="effect",
        capability="example.action",
        name="no-wrap",
    )
    (directory / manifest.EXECUTION_MODULE).write_text("NOTHING = 1\n", encoding="utf-8")
    with pytest.raises(EngineMisuse) as raised:
        engine.install([manifest.read_pack(directory)], FakeBoundary(), scope="local")
    assert "wrap" in str(raised.value)


def test_a_module_no_pack_names_is_imported_untouched(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The finder answers for the modules a pack names, and for nothing else."""
    named, other = target(), target()
    engine.install([pack_for(tmp_path, named)], FakeBoundary(), scope="local")
    loaded = importlib.import_module(other)
    assert getattr(loaded.effect, "wrapped_by_the_pack", False) is False
    assert loaded.VALUE == "original"


def test_the_scope_the_engine_was_installed_with_reaches_the_ask(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The invocation names the scope, and the engine supplies it.

    The pack's wrapper still calls `request(capability, arguments)` — the seam is
    unchanged, and the pack has no parameter with which to choose a scope of its
    own. The scope arrives because the engine bound it.
    """
    name = target()
    boundary = FakeBoundary()
    engine.install([pack_for(tmp_path, name)], boundary, scope="a-scope-of-its-own")
    importlib.import_module(name).effect(1)
    assert boundary.scopes == ["a-scope-of-its-own"]


def test_the_engine_chooses_no_scope_of_its_own(tmp_path: Path, target, engine: Engine) -> None:
    """A default would make a scope somebody typed indistinguishable from one nobody did."""
    name = target()
    with pytest.raises(TypeError):
        engine.install([pack_for(tmp_path, name)], FakeBoundary())  # type: ignore[call-arg]


def test_a_pack_cannot_choose_the_scope_it_is_asked_in(
    tmp_path: Path, target, engine: Engine
) -> None:
    """What a pack is handed has `request(capability, arguments)` and no scope to pass."""
    name = target()
    boundary = FakeBoundary()
    engine.install([pack_for(tmp_path, name)], boundary, scope="local")
    handed = engine._boundary
    assert handed is not None
    with pytest.raises(TypeError):
        handed.request("example.action", {}, scope="chosen-by-the-pack")  # type: ignore[call-arg]


def plant_two_point_pack(root: Path, module: str, *, second: str) -> Any:
    """A pack whose first point is good and whose second names `second`."""
    name = f"pack-two-{next(_names)}"
    directory = root / name
    directory.mkdir()
    (directory / manifest.MANIFEST_FILE).write_text(
        "[pack]\n"
        f'name = "{name}"\n'
        'classification = "convenience"\n'
        "classified_on = 2026-09-14\n"
        "\n[[point]]\n"
        f'module = "{module}"\n'
        'attribute = "effect"\n'
        'capability = "example.action"\n'
        'digest = ["first"]\n'
        f'audit_event = "{module}.effect"\n'
        "\n[[point]]\n"
        f'module = "{module}"\n'
        f'attribute = "{second}"\n'
        'capability = "example.other"\n'
        'digest = ["first"]\n'
        f'audit_event = "{module}.{second}"\n',
        encoding="utf-8",
    )
    (directory / manifest.EXECUTION_MODULE).write_text(INTERPOSE, encoding="utf-8")
    (directory / manifest.CLASSIFICATION_NOTE).write_text("two points, one test\n")
    return manifest.read_pack(directory)


def test_an_install_that_refuses_replaces_nothing(tmp_path: Path, target, engine: Engine) -> None:
    """A refusal half-way through left the earlier points wrapped.

    Everything is resolved and every replacement made before the first
    attribute is replaced, so this leaves the module exactly as it was — which
    is what `commands.py` has always claimed and now does.
    """
    name = target()
    loaded = importlib.import_module(name)
    original = loaded.effect
    with pytest.raises(EngineMisuse) as raised:
        engine.install(
            [plant_two_point_pack(tmp_path, name, second="no_such_attribute")],
            FakeBoundary(),
            scope="local",
        )
    assert "no_such_attribute" in str(raised.value)
    assert loaded.effect is original
    assert getattr(loaded.effect, "wrapped_by_the_pack", False) is False


def test_an_install_that_refuses_on_a_broken_factory_replaces_nothing(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The same rule for the other late refusal: a wrapper that cannot be made."""
    name = target()
    loaded = importlib.import_module(name)
    original = loaded.effect
    pack = plant_two_point_pack(tmp_path, name, second="VALUE")
    (pack.directory / manifest.EXECUTION_MODULE).write_text(
        "_made = 0\n"
        "\n"
        "\ndef wrap(original, capability, boundary):\n"
        "    global _made\n"
        "    _made += 1\n"
        "    if _made > 1:\n"
        '        raise RuntimeError("the second wrapper cannot be made")\n'
        "    return original\n",
        encoding="utf-8",
    )
    with pytest.raises(EngineMisuse) as raised:
        engine.install([manifest.read_pack(pack.directory)], FakeBoundary(), scope="local")
    assert "could not be made" in str(raised.value)
    assert loaded.effect is original


def test_a_point_on_a_module_loaded_later_refuses_inside_the_programs_import(
    tmp_path: Path, target, engine: Engine
) -> None:
    """The one refusal that cannot be found sooner: the attribute did not exist yet."""
    name = target()
    engine.install(
        [plant_two_point_pack(tmp_path, name, second="no_such_attribute")],
        FakeBoundary(),
        scope="local",
    )
    with pytest.raises(EngineMisuse) as raised:
        importlib.import_module(name)
    assert "no_such_attribute" in str(raised.value)


def test_a_stale_bytecode_beside_the_pack_is_never_what_runs(
    tmp_path: Path, target, engine: Engine
) -> None:
    """A `.pyc` planted beside `interpose.py`, matching its size and mtime so the
    ordinary loader would prefer it, must not stand in for the audited source."""
    import importlib.util
    import os
    import py_compile

    name = target()
    directory = plant_pack(
        tmp_path, module=name, attribute="effect", capability="example.action", name="audited"
    )
    source = directory / "interpose.py"
    decoy_text = (
        "def wrap(original, capability, boundary):\n"
        "    def decoy(*a, **k):\n"
        "        return original(*a, **k)\n"
        "    decoy.from_decoy = True\n"
        "    return decoy\n"
    )
    assert len(decoy_text.encode()) <= source.stat().st_size
    decoy = tmp_path / "decoy.py"
    decoy.write_bytes(decoy_text.encode().ljust(source.stat().st_size, b" "))
    stat = source.stat()
    os.utime(decoy, (stat.st_atime, stat.st_mtime))
    cache = Path(importlib.util.cache_from_source(str(source)))
    py_compile.compile(str(decoy), cfile=str(cache), doraise=True)
    assert cache.is_file()
    engine.install([manifest.read_pack(directory)], FakeBoundary(), scope="local")
    loaded = importlib.import_module(name)
    assert getattr(loaded.effect, "wrapped_by_the_pack", False) is True
    assert not getattr(loaded.effect, "from_decoy", False)
