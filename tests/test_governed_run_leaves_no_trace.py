# SPDX-License-Identifier: Apache-2.0
"""Article 9's primary mode is reversible, measured against an ungoverned run.

    "Reversible, which is what article 9 asks of the primary mode. Nothing is
    written to the customer's tree. The interposition lives and dies with the
    process."
                            — the instrumentation chain architecture, 2026-09-14

## What is claimed, and what is not

**Claimed:** a governed run leaves the customer's tree exactly as an ungoverned
run of the same program leaves it. That is the honest form of the sentence
above, and it is why the measurement is a comparison rather than an absolute:
CPython caches the bytecode of every module a program imports, and a program of
two files therefore writes into its own directory whether anybody is governing
it or not. The first version of this test measured a tree of one file — a main
script, which is never cached — so its « byte-identical » assertion had nothing
to write and could not fail. A two-file program falsified the sentence it
printed, which is how this version came to exist.

**Not claimed:** that nothing anywhere is written. The pack's own directory gets
the pack's own bytecode cache, because the pack is a module and the interpreter
caches modules; a pack is code the person running it chose, exactly like a
dependency, and it is not in the tree being governed. What this asserts about it
is that it stays out of that tree, by name.

## The daemon

The contract's own fake, arranged for the golden `allow` scenario, which is the
one that streams a grant: its `given.signal_channel` is absent and therefore
true, its `expect.grant` is `present`, and the outcome is `allow` — the three
conditions the fake requires before it serves a grant on the connection. A
scenario missing any of them answers with a document and no grant, which the
boundary handles but which would prove less here.
"""

from __future__ import annotations

from pathlib import Path

from governed_programs import (
    instrument,
    plain_environment,
    plant_spawn_pack,
    plant_two_file_program,
    tree_shape,
    ungoverned,
)
from sayfirst_contract_stub.stub import Stub
from sayfirst_contract_stub.stub_http import serve


def test_a_governed_run_leaves_what_the_program_leaves_and_nothing_more(
    tmp_path: Path,
) -> None:
    """Two fresh copies of one tree, one run each, and the same tree afterwards."""
    without = plant_two_file_program(tmp_path, "without")
    with_boundary = plant_two_file_program(tmp_path, "with")
    planted = tree_shape(without)
    assert planted == tree_shape(with_boundary), "the two copies did not start equal"
    pack = plant_spawn_pack(tmp_path)

    plainly = ungoverned(without)
    assert plainly.returncode == 0, (plainly.stdout, plainly.stderr)
    assert "helped by the-sibling" in plainly.stdout

    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        governed = instrument(
            "run",
            "--pack",
            str(pack),
            "--socket",
            str(socket_path),
            "--scope",
            "local",
            "--",
            "script.py",
            cwd=with_boundary,
            env=plain_environment(),
        )
    assert governed.returncode == 0, (governed.stdout, governed.stderr)
    assert "helped by the-sibling" in governed.stdout

    # The ask happened: exit zero from a run that never reached the control
    # plane would be the false all-clear article 2 forbids.
    assert stub.decision_count == 1

    after_without, after_with = tree_shape(without), tree_shape(with_boundary)
    assert sorted(after_with) == sorted(after_without)
    assert after_with == after_without
    # Anti-vacuity: the ungoverned run really did write something, so « the two
    # agree » is an agreement about a tree that changed and not about two clean
    # ones. Both must hold a cache, or neither.
    assert after_without != planted, "the ungoverned run wrote nothing to compare against"
    assert any("__pycache__" in name for name in after_without)
    assert any("__pycache__" in name for name in after_with)


def test_the_governed_tree_holds_nothing_of_this_clients_own(tmp_path: Path) -> None:
    """Nothing named after this client, its packs or its engine is left behind."""
    tree = plant_two_file_program(tmp_path, "tree")
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        governed = instrument(
            "run",
            "--pack",
            str(pack),
            "--socket",
            str(socket_path),
            "--scope",
            "local",
            "--",
            "script.py",
            cwd=tree,
            env=plain_environment(),
        )
    assert governed.returncode == 0, (governed.stdout, governed.stderr)
    left = sorted(tree_shape(tree))
    assert left, "a tree with nothing in it proves nothing"
    assert [name for name in left if "sayfirst" in name or "pack" in name] == []
    assert [name for name in left if "interpose" in name] == []


def test_the_governed_program_is_the_one_that_asked(tmp_path: Path) -> None:
    """A run with no matching pack spawns without asking, so the count says so.

    The negative half: it is what stops « the tree is unchanged and the daemon
    was asked » from being read as a property of running any program at all.
    """
    tree = plant_two_file_program(tmp_path, "tree")
    quiet = plant_spawn_pack(tmp_path, name="quiet")
    (quiet / "pack.toml").write_text(
        (quiet / "pack.toml")
        .read_text(encoding="utf-8")
        .replace('module = "subprocess"', 'module = "sayfirst_absent_module"')
        .replace('audit_event = "subprocess.Popen"', 'audit_event = "nothing.spawned"'),
        encoding="utf-8",
    )
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run",
            "--pack",
            str(quiet),
            "--socket",
            str(socket_path),
            "--scope",
            "local",
            "--",
            "script.py",
            cwd=tree,
        )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert stub.decision_count == 0
