# SPDX-License-Identifier: Apache-2.0
"""The `database` pack this distribution ships, proven the way it will run.

Article 9's third convenience pack, following `tests/test_subprocess_pack.py`'s
shape exactly: three levels, because the three things worth proving need
different instruments. `FakeBoundary` is driven in-process. `RefusingBoundary`
is driven the same way, over a recording stand-in for the real function, because
the one safety property this pack has — a refused ask never reaches the open —
is a statement about a call that must NOT happen, and only a recorded original
can say that it did not. `recording_daemon` is driven through the real console
script, because it is the only way to prove the capability and the arguments
actually reach the wire from a real governed process.

This pack's point declares no outcome digest (`interpose.py`'s own docstring
says why: a connection has nothing yet worth digesting), so every granted-path
test below checks `handle.recorded == []` alongside what was asked — the
absence is as much a fact to prove as the ask itself.

The doubles all three of these suites drive their packs against — `FakeBoundary`,
`RefusingBoundary`, `Spy` and the engine harness — are in `tests/pack_doubles.py`,
which records what three copies of them cost. What stays here is this pack's own:
its path, the call shapes it governs, and the capability its refusals name.
"""

from __future__ import annotations

import functools
import os
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from governed_programs import instrument, recording_daemon
from pack_doubles import FakeBoundary, RefusingBoundary, engine_fixture, installed
from pack_doubles import governed_by as _governed_by
from sayfirst_boundary import AskRefused, Denied, Suspended

from sayfirst_cli.instrument import manifest
from sayfirst_cli.instrument.engine import Engine

REPOSITORY = Path(__file__).resolve().parents[1]
PACK = REPOSITORY / "src" / "sayfirst_cli" / "packs" / "database"

#: Captured before any test wraps `sqlite3.connect`, so a test that checks what
#: the wrapper returns is checking against the real function and not whatever
#: `connect` happens to be bound to while it is installed.
REAL_CONNECT = sqlite3.connect


# --- read_pack accepts the real pack ----------------------------------------


def test_the_shipped_pack_reads_as_one_point_governing_connect() -> None:
    pack = manifest.read_pack(PACK)
    assert pack.name == "database"
    assert len(pack.points) == 1
    point = pack.points[0]
    assert (point.module, point.attribute) == ("sqlite3", "connect")
    assert point.capability == "database.open"
    assert point.digest == ("database",)


# --- the wrapper, through the real engine, against a boundary double -------


@pytest.fixture
def engine() -> Iterator[Engine]:
    """One engine, always uninstalled, so no test leaves `sqlite3.connect` wrapped."""
    yield from engine_fixture()


@pytest.fixture
def governed(engine: Engine) -> FakeBoundary:
    """`sqlite3` is already imported at the top of this file, so the engine
    wraps `connect` in place — the same path a program that already did
    `import sqlite3` before `instrument run` reaches it would take."""
    return installed(engine, PACK)


def test_a_string_database_is_asked_and_nothing_is_recorded(governed: FakeBoundary) -> None:
    connection = sqlite3.connect(":memory:")
    connection.close()
    assert governed.asked == [("database.open", {"database": ":memory:"})]
    assert governed.handles[0].recorded == []


def test_a_path_database_is_rendered_with_os_fsdecode(
    governed: FakeBoundary, tmp_path: Path
) -> None:
    target = tmp_path / "sub" / "app.db"
    target.parent.mkdir()
    connection = sqlite3.connect(target)
    connection.close()
    assert governed.asked == [("database.open", {"database": os.fsdecode(target)})]
    assert governed.handles[0].recorded == []


def test_a_bytes_database_is_decoded_to_the_text_it_names(
    governed: FakeBoundary, tmp_path: Path
) -> None:
    """`bytes` IS accepted by the real `sqlite3.connect` (verified: it opens
    and writes a real file), so rendering it with a bare `str()` would send
    its *repr* (`"b'/x/db'"`) rather than the path it names — a second,
    unrelated digest for the database `str`/`Path` already have one for."""
    target = tmp_path / "sub" / "app.db"
    target.parent.mkdir()
    connection = sqlite3.connect(os.fsencode(target))
    connection.close()
    assert governed.asked == [("database.open", {"database": os.fsdecode(target)})]
    assert governed.handles[0].recorded == []
    assert target.is_file()


def test_the_same_database_spelled_two_ways_has_one_rendering(
    governed: FakeBoundary, tmp_path: Path
) -> None:
    """Why the bytes rendering matters: `digest = ["database"]` is the whole of
    what a policy can key on, so one database opened three ways (`str`,
    `bytes`, `Path`) must arrive under one digest, the way `subprocess`'s own
    `args` does for a command line spelled in `str` versus `bytes`."""
    target = tmp_path / "sub" / "app.db"
    target.parent.mkdir()
    sqlite3.connect(str(target)).close()
    sqlite3.connect(os.fsencode(target)).close()
    sqlite3.connect(target).close()
    assert governed.asked == [
        ("database.open", {"database": os.fsdecode(target)}),
        ("database.open", {"database": os.fsdecode(target)}),
        ("database.open", {"database": os.fsdecode(target)}),
    ]


def test_the_wrapper_returns_the_real_connection_untouched(governed: FakeBoundary) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        assert isinstance(connection, sqlite3.Connection)
        connection.execute("create table t (x integer)")
        connection.execute("insert into t values (1)")
        connection.commit()
        assert connection.execute("select x from t").fetchone() == (1,)
    finally:
        connection.close()
    assert governed.handles[0].recorded == []


# --- a refused ask never reaches the real connect, for every call shape ----


#: Every call shape the one wrapped `connect` governs, spelled as a caller
#: spells it, and what `database` a refusal should have seen for it.
def _shapes(path: Path) -> dict[str, tuple[Callable[[], object], str]]:
    return {
        "str": (lambda: sqlite3.connect(":memory:"), ":memory:"),
        "path": (lambda: sqlite3.connect(path), os.fsdecode(path)),
        "bytes": (lambda: sqlite3.connect(os.fsencode(path)), os.fsdecode(path)),
    }


REFUSALS: dict[str, Callable[[], BaseException]] = {
    "denied": lambda: Denied(
        decision_ref="d-refused-1", capability="database.open", reason="the plane said no"
    ),
    "suspended": lambda: Suspended(
        approval_ref="a-1", decision_ref="d-refused-2", capability="database.open"
    ),
    "ask-refused": lambda: AskRefused(
        problem_code="ask-rejected", detail="the question was not accepted"
    ),
}


#: The shared stand-in harness, pointed at the one attribute this pack wraps.
#: This is the pack whose original has no signature `inspect` can parse, which
#: is why `pack_doubles.Spy` guards that call — the union of the three copies it
#: replaced rather than a relaxation of any of them.
governed_by = functools.partial(
    _governed_by, pack=PACK, holder=sqlite3, attribute="connect", original=REAL_CONNECT
)


@pytest.mark.parametrize("shape", sorted(["str", "path", "bytes"]))
@pytest.mark.parametrize("refusal", sorted(REFUSALS))
def test_a_refused_ask_never_reaches_the_real_connect(
    refusal: str, shape: str, tmp_path: Path
) -> None:
    """The one safety property this pack has: a refusal means no open."""
    call, expected = _shapes(tmp_path / "refused.db")[shape]
    boundary = RefusingBoundary(REFUSALS[refusal]())
    with (
        governed_by(boundary) as spy,
        pytest.raises(type(boundary.refusal)) as raised,
    ):
        call()
    assert raised.value is boundary.refusal
    assert spy.calls == []
    assert boundary.asked == [("database.open", {"database": expected})]
    # No file was created: the refusal happened before `original` ever ran.
    assert not (tmp_path / "refused.db").exists()


@pytest.mark.parametrize("shape", sorted(["str", "path", "bytes"]))
def test_the_same_stand_in_opens_the_connection_when_the_ask_is_granted(
    shape: str, tmp_path: Path
) -> None:
    """Anti-vacuity for the refusals above: the same stand-in, a boundary that
    grants, and exactly one recorded call."""
    call, expected = _shapes(tmp_path / "granted.db")[shape]
    boundary = FakeBoundary()
    with governed_by(boundary) as spy:
        connection = call()
        connection.close()
    assert len(spy.calls) == 1
    assert boundary.asked == [("database.open", {"database": expected})]
    assert boundary.handles[0].recorded == []


def test_the_stand_in_is_gone_and_the_real_function_is_back() -> None:
    with governed_by(FakeBoundary()) as spy:
        assert sqlite3.connect is not spy
        assert sqlite3.connect is not REAL_CONNECT
    assert sqlite3.connect is REAL_CONNECT


# --- through `sayfirst instrument run`, against a real daemon on the wire --


DATABASE_PROGRAM = """\
import sqlite3

connection = sqlite3.connect(":memory:")
connection.execute("create table t (x integer)")
connection.close()
"""


def test_a_governed_program_asks_database_open_with_this_packs_capability(
    tmp_path: Path,
) -> None:
    """The pack this distribution actually ships, run through the real console
    script and the real engine, with only the daemon replaced."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(DATABASE_PROGRAM, encoding="utf-8")
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run",
            "--pack",
            str(PACK),
            "--socket",
            str(socket_path),
            "--scope",
            "local",
            "--",
            "app.py",
            cwd=tree,
        )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert len(asks) == 1, asks
    assert asks[0]["capability"] == "database.open"
