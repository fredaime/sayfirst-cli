# SPDX-License-Identifier: Apache-2.0
"""An interposed call's own implementation is not a second path around the pack.

The subprocess pack interposes `subprocess.Popen` and names the other ways this
interpreter creates a process, so the verifier counts an effect that took one
of them as an effect it could not judge. But `Popen` creates its own process
through two of those ways: `os.posix_spawn` whenever it can — for an executable
named with a directory, by default from Python 3.14 and with `close_fds=False`
before — and otherwise `_posixsubprocess.fork_exec`, which raises an event of
its own from Python 3.14. One governed spawn therefore raised two events, and
the run reported an effect it could not judge, and status 7, for a program that
did nothing around the pack.

A pack now names such events as its point's `inner_events`, and the verifier
pairs one with the call it just judged when it is the very next event that
thread raises and it carries the argument vector that call was given. Anything
else is counted: a direct spawn of another command, a second inner event, an
inner event after anything else the thread raised.

And the event Python 3.14 added is a path of its own: `multiprocessing` starts
its processes through it, and before the pack named it such a start reached the
world with nothing counted and the run still answered `0`.

The end-to-end case against a real daemon is the control plane's
(`test_a_spawn_popen_makes_through_posix_spawn_is_one_effect`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from canned_daemon import answering_by_path
from documents import no_evidence_page, recorded_effect_page
from governed_programs import instrument, plant_spawn_pack

from sayfirst_cli import exit_codes
from sayfirst_cli.instrument import harness, manifest

SHIPPED = Path(__file__).resolve().parents[1] / "src/sayfirst_cli/packs/subprocess"
SPAWN = "process.spawn"
POSIX_SPAWN = "os.posix_spawn"
FORK_EXEC = "_posixsubprocess.fork_exec"

#: Python 3.14 is the first interpreter whose fork-and-exec raises an event at all.
ONLY_WHERE_FORK_EXEC_IS_AUDITED = pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="before Python 3.14 `_posixsubprocess.fork_exec` raises no audit event",
)


def _popen(args: object) -> harness.Judged:
    """A judged `Popen`, as its audit event carries it: `(executable, args, cwd, env)`."""
    return harness.Judged(frozenset({POSIX_SPAWN, FORK_EXEC}), (None, args, None, None))


# --- the pairing rule ---------------------------------------------------------


def test_the_inner_spawn_of_the_same_vector_is_the_same_act() -> None:
    assert harness.the_same_act(
        _popen(["/bin/true", "-x"]), POSIX_SPAWN, ("/bin/true", ["/bin/true", "-x"], None)
    )


def test_a_shell_command_is_paired_by_the_vector_popen_audits() -> None:
    """`shell=True` is audited as the vector it spawns: `SHELL -c COMMAND`."""
    audited = ["/bin/sh", "-c", "echo hi"]
    assert harness.the_same_act(_popen(audited), POSIX_SPAWN, ("/bin/sh", list(audited), None))


def test_the_fork_exec_shape_is_paired_by_its_vector() -> None:
    """`fork_exec` carries every place it will look for the program, then the vector."""
    assert harness.the_same_act(
        _popen(["true"]), FORK_EXEC, ((b"/usr/bin/true", b"/bin/true"), ["true"])
    )


def test_bytes_and_paths_are_read_as_the_names_they_are() -> None:
    assert harness.the_same_act(
        _popen([b"/bin/cat", Path("/tmp/x")]), POSIX_SPAWN, ("/bin/cat", ["/bin/cat", "/tmp/x"])
    )


def test_another_command_is_another_act() -> None:
    assert not harness.the_same_act(
        _popen(["/bin/true"]), POSIX_SPAWN, ("/bin/rm", ["/bin/rm", "-rf", "/tmp/x"], None)
    )


def test_an_event_the_point_does_not_name_as_its_own_is_another_act() -> None:
    assert not harness.the_same_act(_popen(["/bin/true"]), "os.system", ("/bin/true",))
    assert not harness.the_same_act(
        harness.Judged(frozenset(), (None, ["/bin/true"], None, None)),
        POSIX_SPAWN,
        ("/bin/true", ["/bin/true"], None),
    )


def test_a_vector_that_is_not_a_list_or_a_tuple_is_not_read() -> None:
    """Iterating anything else could run the program's code, or use up its argument."""
    consumed: list[str] = []

    def vector():
        consumed.append("read")
        yield "/bin/true"

    assert not harness.the_same_act(
        _popen(["/bin/true"]), POSIX_SPAWN, ("/bin/true", vector(), None)
    )
    assert consumed == []
    assert not harness.the_same_act(_popen(["/bin/true"]), POSIX_SPAWN, ("/bin/true",))


# --- the declaration is the pack's --------------------------------------------


def test_the_shipped_pack_names_popens_own_events_and_the_one_314_added() -> None:
    pack = manifest.read_pack(SHIPPED)
    inner = harness.inner_events(pack)
    uninterposed = harness.uninterposed_events(pack)
    assert set(inner[0]) == {POSIX_SPAWN, FORK_EXEC}, inner
    assert FORK_EXEC in uninterposed[0], uninterposed


def _a_pack_declaring(root: Path, lines: str) -> manifest.Pack:
    directory = plant_spawn_pack(root)
    manifest_file = directory / manifest.MANIFEST_FILE
    manifest_file.write_text(manifest_file.read_text(encoding="utf-8") + lines, encoding="utf-8")
    return manifest.read_pack(directory)


def test_an_inner_event_must_be_one_the_point_names_as_uninterposed(tmp_path: Path) -> None:
    """Pairing only stops a named event being counted; naming only one side declares nothing."""
    pack = _a_pack_declaring(
        tmp_path,
        f'{harness.UNINTERPOSED} = ["os.system"]\n{harness.INNER} = ["{POSIX_SPAWN}"]\n',
    )
    with pytest.raises(manifest.PackInvalid, match=harness.INNER):
        harness.inner_events(pack)


@pytest.mark.parametrize("declared", ["[]", '"os.posix_spawn"', '[""]', "[1]"])
def test_a_declaration_this_reader_cannot_read_is_refused(tmp_path: Path, declared: str) -> None:
    pack = _a_pack_declaring(
        tmp_path, f'{harness.UNINTERPOSED} = ["{POSIX_SPAWN}"]\n{harness.INNER} = {declared}\n'
    )
    with pytest.raises(manifest.PackInvalid, match=harness.INNER):
        harness.inner_events(pack)


def test_a_point_that_names_none_pairs_none(tmp_path: Path) -> None:
    pack = _a_pack_declaring(tmp_path, f'{harness.UNINTERPOSED} = ["{POSIX_SPAWN}"]\n')
    assert harness.inner_events(pack) == {}


# --- the run, against the shipped pack ----------------------------------------


def _verified(tmp_path: Path, program: str, *, reads: int = 1) -> tuple[int, str, str]:
    """`verify --ungoverned` of one program under the shipped subprocess pack."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(program, encoding="utf-8")
    pages = [no_evidence_page()] + [recorded_effect_page(SPAWN)] * reads
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, pages)}) as address:
        finished = instrument(
            "verify",
            "--pack",
            str(SHIPPED),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    return finished.returncode, finished.stdout, finished.stderr


def test_a_spawn_popen_makes_through_posix_spawn_is_one_effect(tmp_path: Path) -> None:
    code, out, err = _verified(
        tmp_path,
        "import subprocess\nsubprocess.run(['/bin/true'], check=True, close_fds=False)\n",
    )
    assert code == 0, (out, err)
    assert harness.UNJUDGED not in out, out


def test_a_spawn_popen_makes_through_fork_exec_is_one_effect(tmp_path: Path) -> None:
    """A working directory keeps `Popen` off `posix_spawn`, on every interpreter."""
    code, out, err = _verified(
        tmp_path, "import subprocess\nsubprocess.run(['/bin/true'], check=True, cwd='/')\n"
    )
    assert code == 0, (out, err)
    assert harness.UNJUDGED not in out, out


@ONLY_WHERE_FORK_EXEC_IS_AUDITED
def test_a_direct_spawn_after_a_governed_one_is_counted_even_of_the_same_command(
    tmp_path: Path,
) -> None:
    """The pairing belongs to the event raised next, never to one raised later.

    `Popen` given a working directory raises its own `fork_exec`, which takes the
    pairing; the direct `posix_spawn` that follows is a second process, created
    past the pack, and it is counted though it runs the very same command.
    """
    code, out, err = _verified(
        tmp_path,
        "import os\nimport subprocess\n"
        "subprocess.run(['/bin/true'], check=True, cwd='/')\n"
        "pid = os.posix_spawn('/bin/true', ['/bin/true'], os.environ)\n"
        "print('second process status:', os.waitpid(pid, 0)[1], flush=True)\n",
    )
    assert "second process status: 0" in out + err, (out, err)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (out, err)
    assert f"{harness.UNJUDGED}: 1" in out, out


@ONLY_WHERE_FORK_EXEC_IS_AUDITED
def test_a_process_multiprocessing_starts_is_counted(tmp_path: Path) -> None:
    """The start method `multiprocessing` uses by default on Linux from Python 3.14."""
    code, out, err = _verified(
        tmp_path,
        "import multiprocessing\n"
        "import os\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    child = multiprocessing.get_context('forkserver').Process(target=os.getpid)\n"
        "    child.start()\n"
        "    child.join()\n"
        "    print('child exit:', child.exitcode, flush=True)\n",
        reads=0,
    )
    assert "child exit: 0" in out + err, (out, err)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (out, err)
    assert f"{harness.UNJUDGED}:" in out, out
