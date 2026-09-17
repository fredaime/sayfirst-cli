# SPDX-License-Identifier: Apache-2.0
"""The `subprocess` pack this distribution ships, proven the way it will run.

Not `governed_programs.SPAWN_INTERPOSE`, which is a fixture `test_instrument_run.py`
wrote for the launcher's own tests before any pack shipped. This is the pack
`src/sayfirst_cli/packs/subprocess`, read the way `sayfirst instrument run
--pack` reads it.

Three levels, because the three things worth proving need different instruments.
`FakeBoundary` (the same double `tests/test_engine.py` hands the real `Engine`
— `request` as a context manager yielding something with `record_outcome`, and
nothing else) is driven in-process, because the outcome digest `record_outcome`
receives is never sent to a real daemon (`launch.py` wires no sink for it) and
an end-to-end run could not observe it. `RefusingBoundary` is driven the same
way, over a recording stand-in for the real class, because the one safety
property this pack has — a refused ask never reaches the spawn — is a statement
about a call that must NOT happen, and only a recorded original can say that it
did not. `recording_daemon` (the fake `test_instrument_run.py` already uses) is
driven through the real console script, because it is the only way to prove the
capability and the arguments actually reach the wire from a real governed
process, rather than from a wrapper called directly.

The doubles all three of these suites drive their packs against — `FakeBoundary`,
`RefusingBoundary`, `Spy` and the engine harness — are in `tests/pack_doubles.py`,
which records what three copies of them cost. What stays here is this pack's own:
its path, the call shapes it governs, and the capability its refusals name.
"""

from __future__ import annotations

import functools
import hashlib
import shutil
import subprocess
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
PACK = REPOSITORY / "src" / "sayfirst_cli" / "packs" / "subprocess"

#: Captured before any test wraps `subprocess.Popen`, so a test that checks
#: what the wrapper returns is checking against the real class and not
#: whatever `subprocess.Popen` happens to be bound to while it is installed.
REAL_POPEN = subprocess.Popen


# --- read_pack accepts the real pack --------------------------------------


def test_the_shipped_pack_reads_as_one_point_governing_popen() -> None:
    pack = manifest.read_pack(PACK)
    assert pack.name == "subprocess"
    assert len(pack.points) == 1
    point = pack.points[0]
    assert (point.module, point.attribute) == ("subprocess", "Popen")
    assert point.capability == "process.spawn"
    assert point.digest == ("args",)


# --- the wrapper, through the real engine, against a boundary double -------


@pytest.fixture
def engine() -> Iterator[Engine]:
    """One engine, always uninstalled, so no test leaves `subprocess.Popen` wrapped."""
    yield from engine_fixture()


@pytest.fixture
def governed(engine: Engine) -> FakeBoundary:
    """`subprocess` is already imported at the top of this file, so the engine
    wraps `Popen` in place — the same path a program that already did
    `import subprocess` before `instrument run` reaches it would take."""
    return installed(engine, PACK)


def test_popen_asks_and_records_the_pid_it_spawned(governed: FakeBoundary) -> None:
    process = subprocess.Popen(["true"])
    process.wait()
    assert governed.asked == [("process.spawn", {"args": ["true"]})]
    expected = hashlib.sha256(f"pid:{process.pid}".encode()).hexdigest()
    assert governed.handles[0].recorded == [expected]


def test_run_call_and_check_output_all_go_through_the_one_wrapped_popen(
    governed: FakeBoundary,
) -> None:
    """`run`, `call` and `check_output` declare no point of their own — they
    are governed because they all call the module's own global `Popen`."""
    subprocess.run(["true"], check=True)
    subprocess.call(["true"])
    subprocess.check_output(["true"])
    assert [capability for capability, _ in governed.asked] == ["process.spawn"] * 3
    assert [arguments for _, arguments in governed.asked] == [{"args": ["true"]}] * 3
    assert len(governed.handles) == 3
    assert all(handle.recorded for handle in governed.handles)


def test_a_string_command_line_is_sent_as_a_string_not_a_list(governed: FakeBoundary) -> None:
    process = subprocess.Popen("true", shell=True)
    process.wait()
    assert governed.asked == [("process.spawn", {"args": "true"})]


# --- one command line, however the caller spelled it -----------------------

#: The `true` program by path, for the shapes that need a path rather than a
#: name. Looked up rather than spelled: it is `/usr/bin/true` here and
#: `/bin/true` elsewhere.
TRUE = shutil.which("true")


def test_a_bytes_command_line_is_sent_as_the_text_it_names(governed: FakeBoundary) -> None:
    """`bytes` IS a sequence — of integers — so an unguarded sequence branch
    sends the plane a list of byte codes for a command line a second caller
    sends as a string."""
    subprocess.Popen(b"true", shell=True).wait()
    assert governed.asked == [("process.spawn", {"args": "true"})]


def test_a_list_of_bytes_is_sent_as_a_list_of_text(governed: FakeBoundary) -> None:
    subprocess.Popen([b"true"]).wait()
    assert governed.asked == [("process.spawn", {"args": ["true"]})]


def test_a_path_command_line_is_sent_as_its_text(governed: FakeBoundary) -> None:
    assert TRUE is not None, "no `true` program on PATH"
    subprocess.Popen(Path(TRUE)).wait()
    assert governed.asked == [("process.spawn", {"args": TRUE})]


def test_a_mixed_sequence_is_rendered_element_by_element(governed: FakeBoundary) -> None:
    """One list, three spellings of a string, one rendering of the three."""
    assert TRUE is not None, "no `true` program on PATH"
    subprocess.Popen([Path(TRUE), b"ignored", "ignored"]).wait()
    assert governed.asked == [("process.spawn", {"args": [TRUE, "ignored", "ignored"]})]


def test_a_bytearray_element_is_decoded_even_where_popen_refuses_the_type(
    governed: FakeBoundary,
) -> None:
    """The rendering happens before the spawn, so it can be read even here:
    `Popen` itself will not take a `bytearray`, and the ask that preceded its
    refusal still named the command line as text rather than as
    `bytearray(b'true')`."""
    with pytest.raises(TypeError):
        subprocess.Popen([bytearray(b"true")])
    assert governed.asked == [("process.spawn", {"args": ["true"]})]


def test_the_same_spawn_spelled_two_ways_has_one_rendering(governed: FakeBoundary) -> None:
    """Why any of the above matters: `digest = ["args"]` is the whole of what a
    policy can key on, so two callers spawning one process must not arrive
    under two unrelated digests."""
    subprocess.Popen([b"true"]).wait()
    subprocess.Popen(["true"]).wait()
    assert [arguments for _, arguments in governed.asked] == [{"args": ["true"]}] * 2


def test_the_wrapper_returns_the_real_popen_so_the_with_form_still_works(
    governed: FakeBoundary,
) -> None:
    with subprocess.Popen(["true"]) as process:
        process.wait()
    assert isinstance(process, REAL_POPEN)
    assert governed.handles[0].recorded


# --- a refused ask never reaches the spawn, for every call shape ------------


#: Every call shape the one wrapped `Popen` governs, spelled as a caller spells
#: it. `run`, `call` and `check_output` declare no point of their own — they
#: reach the module's own global `Popen`, which is the name the pack wraps.
SPAWNS: dict[str, Callable[[], object]] = {
    "Popen": lambda: subprocess.Popen(["true"]).wait(),
    "call": lambda: subprocess.call(["true"]),
    "check_output": lambda: subprocess.check_output(["true"]),
    "run": lambda: subprocess.run(["true"], check=True),
}

#: One refusal of each kind the boundary raises out of the ask. Built per test
#: rather than shared, so no test raises another's exception object. The fourth
#: kind, `CouldNotAsk`, takes the same path through the wrapper as these three:
#: whatever the ask raises, the spawn is on the far side of the `with`.
REFUSALS: dict[str, Callable[[], BaseException]] = {
    "denied": lambda: Denied(
        decision_ref="d-refused-1", capability="process.spawn", reason="the plane said no"
    ),
    "suspended": lambda: Suspended(
        approval_ref="a-1", decision_ref="d-refused-2", capability="process.spawn"
    ),
    "ask-refused": lambda: AskRefused(
        problem_code="ask-rejected", detail="the question was not accepted"
    ),
}


#: The shared stand-in harness, pointed at the one attribute this pack wraps.
#: The double is `pack_doubles.governed_by`; what is this suite's own is which
#: attribute of which module it replaces, and with what.
governed_by = functools.partial(
    _governed_by, pack=PACK, holder=subprocess, attribute="Popen", original=REAL_POPEN
)


@pytest.mark.parametrize("shape", sorted(SPAWNS))
@pytest.mark.parametrize("refusal", sorted(REFUSALS))
def test_a_refused_ask_never_reaches_the_real_popen(refusal: str, shape: str) -> None:
    """The one safety property this pack has: a refusal means no process.

    Three things at once, because two of them alone would pass on a pack that
    spawns first and asks afterwards: the refusal reaches the caller unchanged,
    the ask was made once with the rendered command line, and the original was
    never called at all.
    """
    boundary = RefusingBoundary(REFUSALS[refusal]())
    with (
        governed_by(boundary) as spy,
        pytest.raises(type(boundary.refusal)) as raised,
    ):
        SPAWNS[shape]()
    assert raised.value is boundary.refusal
    assert spy.calls == []
    assert boundary.asked == [("process.spawn", {"args": ["true"]})]


@pytest.mark.parametrize("shape", sorted(SPAWNS))
def test_the_same_stand_in_records_the_call_when_the_ask_is_granted(shape: str) -> None:
    """Anti-vacuity for the refusals above: the same stand-in, a boundary that
    grants, and exactly one recorded call — so `spy.calls == []` there is the
    refusal's doing and not a harness that wired the stand-in to nothing."""
    boundary = FakeBoundary()
    with governed_by(boundary) as spy:
        SPAWNS[shape]()
    assert len(spy.calls) == 1
    assert boundary.asked == [("process.spawn", {"args": ["true"]})]


def test_the_stand_in_is_gone_and_the_real_class_is_back() -> None:
    """The harness leaves nothing behind, which every test above depends on."""
    with governed_by(FakeBoundary()) as spy:
        assert subprocess.Popen is not spy
        assert subprocess.Popen is not REAL_POPEN
    assert subprocess.Popen is REAL_POPEN


# --- through `sayfirst instrument run`, against a real daemon on the wire --


SPAWNING_PROGRAM = """\
import subprocess

subprocess.run(["true"], check=True)
"""


def test_a_governed_program_asks_process_spawn_with_this_packs_capability(
    tmp_path: Path,
) -> None:
    """The pack this distribution actually ships, run through the real console
    script and the real engine, with only the daemon replaced."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_PROGRAM, encoding="utf-8")
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
    assert asks[0]["capability"] == "process.spawn"
