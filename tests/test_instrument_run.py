# SPDX-License-Identifier: Apache-2.0
"""What `sayfirst instrument` reports, and the one code it deliberately does not own.

The launcher runs somebody else's program. So the codes it produces come from
two places and never from a third: the invocation's own mistakes, which are this
client's to report (64, and argparse's 2), and the governed program's ending,
which is the program's and is passed through untouched.

The consequence worth writing down is the traceback. A refusal the boundary
raises inside a governed program is that program's exception, and an uncaught
exception ends a process with a traceback and exit 1. In this client 1 is the
published code for « deny », which is exactly what happened here — the control
plane denied, and the program stopped — so the reading is right by accident of
the numbering and correct on purpose: the launcher did not translate it. A
program that wants any other rendering catches the exception, which is the
boundary's whole shape.
"""

from __future__ import annotations

import atexit
import io
import os
import sys
from pathlib import Path

import pytest
from canned_daemon import answering_by_path
from documents import no_evidence_page
from governed_programs import (
    HELPER,
    SIBLING_MODULE_APP,
    SIBLING_ONLY_APP,
    SPAWNING_APP,
    instrument,
    plant_pack,
    plant_spawn_pack,
    recording_daemon,
)
from sayfirst_contract_stub.stub import Stub
from sayfirst_contract_stub.stub_http import serve

from sayfirst_cli import exit_codes
from sayfirst_cli.instrument import commands, launch


def refuse(*argv: str) -> tuple[int, str, str]:
    """A refusal needs no process: nothing is installed and nothing is run."""
    out, err = io.StringIO(), io.StringIO()
    code = commands.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_the_programs_own_exit_code_reaches_the_shell_unchanged(tmp_path: Path) -> None:
    """The launcher does not own it: 3 is this client's code for « refused », and
    here it means only that the program said 3."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text("import sys\n\nsys.exit(3)\n", encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=tree,
    )
    assert finished.returncode == 3, (finished.stdout, finished.stderr)
    assert "Traceback" not in finished.stderr


def test_a_program_that_ends_quietly_exits_zero(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text("pass\n", encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=tree,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)


def test_a_program_that_exits_with_a_message_says_it_and_exits_one(tmp_path: Path) -> None:
    """`SystemExit` carrying something that is not a code, read as the interpreter reads it."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text('raise SystemExit("stopped short")\n', encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=tree,
    )
    assert finished.returncode == 1
    assert "stopped short" in finished.stderr


def test_a_denied_effect_stops_the_program_with_its_own_exception(tmp_path: Path) -> None:
    """The boundary's refusal is the program's to handle, and this one handles none."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("deny")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run",
            "--pack",
            str(pack),
            "--socket",
            str(socket_path),
            "--scope",
            "local",
            "--",
            "app.py",
            cwd=tree,
        )
    assert stub.decision_count == 1
    assert finished.returncode == 1
    assert "Denied" in finished.stderr
    assert "Traceback" in finished.stderr
    # The effect did not happen: the body of the boundary's shape never ran.
    assert "denied: process.spawn" in finished.stderr


def test_the_module_form_of_a_target_runs_a_module(tmp_path: Path) -> None:
    """`-m name args…`, in the interpreter's own spelling for it."""
    (tmp_path / "sayfirst_target_app.py").write_text(
        "import sys\n\nprint('ran', sys.argv[1:])\nsys.exit(7)\n", encoding="utf-8"
    )
    pack = plant_spawn_pack(tmp_path)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "-m",
        "sayfirst_target_app",
        "one",
        "two",
        env=environment,
    )
    assert finished.returncode == 7, (finished.stdout, finished.stderr)
    assert "ran ['one', 'two']" in finished.stdout


def test_a_pack_directory_that_is_not_there_is_a_misuse(tmp_path: Path) -> None:
    """Exit 64, with the manifest's own sentence and the path that was named."""
    code, out, err = refuse(
        "run",
        "--pack",
        str(tmp_path / "absent"),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert str(tmp_path / "absent") in err
    assert "pack.toml" in err
    assert out == ""


def test_an_invalid_manifest_is_a_misuse_and_names_the_member(tmp_path: Path) -> None:
    pack = plant_spawn_pack(tmp_path)
    (pack / "pack.toml").write_text(
        (pack / "pack.toml")
        .read_text(encoding="utf-8")
        .replace('capability = "process.spawn"', 'capability = "subprocess"'),
        encoding="utf-8",
    )
    code, _, err = refuse(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert "capability" in err


def test_a_system_profile_that_names_no_account_is_a_misuse(tmp_path: Path) -> None:
    """The same rule the reads obey: a profile that cannot say what it verifies is not one."""
    pack = plant_spawn_pack(tmp_path)
    code, _, err = refuse(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--mode",
        "system",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert "names the account" in err


def test_a_run_with_nothing_after_the_separator_is_a_misuse(tmp_path: Path) -> None:
    """A launcher with no program to launch has nothing to report but the mistake."""
    pack = plant_spawn_pack(tmp_path)
    code, _, err = refuse(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "d.sock"), "--scope", "local", "--"
    )
    assert code == exit_codes.EXIT_MISUSE
    assert "--" in err


def test_the_module_form_without_a_module_name_is_a_misuse(tmp_path: Path) -> None:
    pack = plant_spawn_pack(tmp_path)
    code, _, err = refuse(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "-m",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert "-m" in err


def test_a_daemon_account_this_host_has_not_got_is_never_a_denial(tmp_path: Path) -> None:
    """Articles 1 and 2: no question was asked, so the answer is « could not ask ».

    The target is a script that exists, because the subject here is the account:
    the launcher resolves the target first, so a program that is not there would
    be reported as the misuse it is and this test would prove something else.
    """
    pack = plant_spawn_pack(tmp_path)
    (tmp_path / "app.py").write_text("pass\n", encoding="utf-8")
    code, _, err = refuse(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--mode",
        "system",
        "--daemon-user",
        "sayfirst-no-such-account",
        "--",
        str(tmp_path / "app.py"),
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert code != exit_codes.EXIT_DENY
    assert "could not ask" in err


def test_apply_refuses_with_the_reason_it_does_nothing() -> None:
    """Article 9's later option keeps its name, and says it is not that option yet."""
    code, out, err = refuse("apply")
    assert code == exit_codes.EXIT_MISUSE
    assert err == (
        "instrument apply is reserved for the committed code modification, which does "
        "not exist yet; use `instrument run`, the reversible mode (architecture reading, "
        "2026-09-14)\n"
    )
    assert out == ""


def test_apply_refuses_whatever_it_is_handed(tmp_path: Path) -> None:
    """It refuses the act, not the spelling: nothing it is given makes it run."""
    code, _, err = refuse("apply", "--pack", str(tmp_path), "--", "app.py")
    assert code == exit_codes.EXIT_MISUSE
    assert "reserved for the committed code modification" in err


def test_verify_is_a_verb_now_and_no_longer_a_reserved_refusal() -> None:
    """Layer 3 arrived, so `verify` reads arguments where it used to refuse the act.

    Named with nothing after it, it is argparse's own usage error — 2, which is
    not one of this client's outcomes — and no longer 64 with a sentence about
    a verifier that does not exist. What it now answers is in
    `tests/test_instrument_verify.py`.
    """
    assert "verify" not in commands.RESERVED
    with pytest.raises(SystemExit) as raised:
        commands.main(["verify"], out=io.StringIO(), err=io.StringIO())
    assert raised.value.code == exit_codes.EXIT_PARSER_USAGE


def test_the_help_names_the_three_verbs_and_claims_no_fourth() -> None:
    """Article 2: a help text is a claim about what exists."""
    parser = commands.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])
    text = parser.format_help()
    for verb in ("run", "verify", "apply"):
        assert verb in text


def test_an_unknown_verb_is_the_parsers_own_usage_error() -> None:
    """Exit 2 is argparse's, and it is not one of this client's outcomes."""
    with pytest.raises(SystemExit) as raised:
        commands.main(["compile"], out=io.StringIO(), err=io.StringIO())
    assert raised.value.code == exit_codes.EXIT_PARSER_USAGE


# --- The import path the program would have had ---------------------------------


def test_a_script_can_import_the_module_beside_it(tmp_path: Path) -> None:
    """CPython puts a script's own directory first on the import path; so does this.

    Measured as the defect that made this test exist: through the console script
    a two-file program raised `ModuleNotFoundError: No module named 'helper'`
    and exited 1, while `python app.py` in the same directory worked.
    """
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SIBLING_ONLY_APP, encoding="utf-8")
    (tree / "helper.py").write_text(HELPER, encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=tree,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "helped by the-sibling" in finished.stdout


def test_a_script_named_from_elsewhere_still_imports_its_own_neighbours(tmp_path: Path) -> None:
    """It is the SCRIPT's directory, not the working directory, as the interpreter does."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SIBLING_ONLY_APP, encoding="utf-8")
    (tree / "helper.py").write_text(HELPER, encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        str(tree / "app.py"),
        cwd=elsewhere,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "helped by the-sibling" in finished.stdout


def test_the_module_form_can_import_the_module_beside_it(tmp_path: Path) -> None:
    """`-m` gets the working directory first on the import path, as the interpreter does.

    No `PYTHONPATH` is set, on purpose: it would supply what the launcher is
    supposed to supply, which is how the first version of this passed.
    """
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "mod_app.py").write_text(SIBLING_MODULE_APP, encoding="utf-8")
    (tree / "helper.py").write_text(HELPER, encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "-m",
        "mod_app",
        cwd=tree,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "helped by the-sibling" in finished.stdout


def test_the_argv_and_the_path_entry_are_the_programs_own(tmp_path: Path) -> None:
    """What the program sees is what the interpreter would have given it."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(
        "import sys\n\nprint('argv', sys.argv)\nprint('head', sys.path[0])\n", encoding="utf-8"
    )
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        "one",
        cwd=tree,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "argv ['app.py', 'one']" in finished.stdout
    assert f"head {tree}" in finished.stdout


# --- The program's lifecycle does not end when its main module returns ---------


#: A program that leaves work behind it. Its handler reads the two things the
#: interpreter hands a program — the arguments it was given and the directory
#: its own modules are found on — and it runs after the main module has
#: returned, which is the whole point of it.
EXIT_HANDLER_APP = """\
import atexit
import sys


def at_exit():
    print("at exit argv", sys.argv)
    print("at exit head", sys.path[0])
    import helper

    print("at exit helper", helper.NAME)


atexit.register(at_exit)
print("in main argv", sys.argv)
"""


def a_tree_whose_exit_handler_reads_its_own_state(root: Path, name: str = "tree") -> Path:
    """The two-file program again, with the import moved into the exit handler.

    Two files rather than one for the same reason the sibling tests give: a
    main script is found by name and never imported, so only a second file can
    say whether the import path the handler runs on is the program's own.
    """
    tree = root / name
    tree.mkdir(parents=True)
    (tree / "app.py").write_text(EXIT_HANDLER_APP, encoding="utf-8")
    (tree / "helper.py").write_text(HELPER, encoding="utf-8")
    return tree


def test_an_exit_handler_sees_the_programs_own_argv_and_imports_its_sibling(
    tmp_path: Path,
) -> None:
    """A handler registered by the program is the program, and gets what the program gets.

    Measured as the defect: the hand-off put the launcher's `sys.argv` and
    `sys.path` back as soon as the main module RETURNED, which is not when the
    program ends. The handler then read the `sayfirst` command line as its own
    arguments and could not import the module sitting beside it — an ordinary
    program changed by being governed, without ever asking the boundary.
    """
    tree = a_tree_whose_exit_handler_reads_its_own_state(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        "one",
        cwd=tree,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    # Anti-vacuity: the main module read its own arguments before the defect
    # and reads them after it, so a test asserting only the second line would
    # pass on a hand-off that gave the program nothing at all.
    assert "in main argv ['app.py', 'one']" in finished.stdout
    assert "at exit argv ['app.py', 'one']" in finished.stdout, finished.stdout
    assert f"at exit head {tree}" in finished.stdout, finished.stdout
    assert "at exit helper the-sibling" in finished.stdout, (finished.stdout, finished.stderr)
    assert "Traceback" not in finished.stderr


#: The other thing that outlives a main module: a thread the program started
#: and did not join. It reads what the handler reads, half a second after the
#: main module's last statement, which is the only way this moment can be
#: timed from inside the program.
LATE_THREAD_APP = """\
import sys
import threading
import time


def late():
    time.sleep(0.5)
    print("in thread argv", sys.argv)
    import helper

    print("in thread helper", helper.NAME)


threading.Thread(target=late).start()
print("in main argv", sys.argv)
"""


def test_a_thread_that_outlives_the_main_module_keeps_the_programs_own_state(
    tmp_path: Path,
) -> None:
    """A thread the interpreter will wait for is the program too, and gets what it gets.

    The same defect as the exit handler's and the same fix: the launcher's
    state went back the instant the main module returned, and a thread still
    running read the `sayfirst` command line as its arguments. The half second
    is what makes the thread late rather than concurrent — it is the one thing
    here that can only be timed — and a thread that ran early would read the
    right arguments for the wrong reason, which is why the run above it asserts
    the same claim at a moment that needs no clock.
    """
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(LATE_THREAD_APP, encoding="utf-8")
    (tree / "helper.py").write_text(HELPER, encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        "one",
        cwd=tree,
    )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "in thread argv ['app.py', 'one']" in finished.stdout, finished.stdout
    assert "in thread helper the-sibling" in finished.stdout, (finished.stdout, finished.stderr)


def test_the_verified_hand_off_leaves_the_exit_handler_the_programs_own_state(
    tmp_path: Path,
) -> None:
    """The same claim on the path that runs the handlers itself, which is later still.

    `verify` does not leave the exit handlers to the interpreter: the harness
    runs them while its watch is still armed, after the hand-off has already
    returned. So the restore has to outlast that too, and a fix that only
    worked on the plain `run` path would pass the test above and fail here.

    Ungoverned, and against a chain holding nothing: this test is about what
    the program sees, not about a verdict, and the program asks the boundary
    for nothing. Its output reaches the error stream because that is where
    `verify` puts the program's own, keeping stdout for the answer.
    """
    tree = a_tree_whose_exit_handler_reads_its_own_state(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    routes = {"/scopes/": (200, no_evidence_page())}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        finished = instrument(
            "verify",
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            "one",
            cwd=tree,
        )
    assert "in main argv ['app.py', 'one']" in finished.stderr
    assert "at exit argv ['app.py', 'one']" in finished.stderr, finished.stderr
    assert f"at exit head {tree}" in finished.stderr, finished.stderr
    assert "at exit helper the-sibling" in finished.stderr, (finished.stdout, finished.stderr)


def test_the_launchers_own_state_comes_back_once_the_program_is_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deferred is not abandoned: the last thing the register holds is the restore.

    The other half of the fix, and the half a `run` through a process cannot
    show, because the process ends on the same breath. `atexit` runs its
    register last in, first out, so the restore is registered BEFORE the
    program starts and every handler the program registers afterwards runs
    ahead of it. That order is what this asserts, by standing in for the
    register: the handlers are replayed the way the interpreter replays them,
    and the launcher's own arguments and import path are back when the last
    one has run.

    In process, and against a stand-in for the register, because running the
    real one here would run this test session's own handlers. The stand-in is
    the register in both the ways the launcher uses it — what is added to it,
    and how many things it holds — and the replay is the interpreter's own
    order; nothing else about it is borrowed.
    """
    registered: list[object] = []

    def register(function: object) -> object:
        registered.append(function)
        return function

    monkeypatch.setattr(atexit, "register", register)
    monkeypatch.setattr(atexit, "_ncallbacks", lambda: len(registered))
    tree = a_tree_whose_exit_handler_reads_its_own_state(tmp_path, name="in-process")
    monkeypatch.syspath_prepend(str(tree))
    mine_argv, mine_path = list(sys.argv), list(sys.path)
    try:
        launch.hand_over([str(tree / "app.py"), "one"], err=io.StringIO())
        # The program is not done, so its own state still stands.
        assert sys.argv == [str(tree / "app.py"), "one"], sys.argv
        # Last in, first out: the program's handler, and then the restore.
        for callback in reversed(registered):
            callback()  # type: ignore[operator]
        after_argv, after_path = list(sys.argv), list(sys.path)
    finally:
        sys.argv[:] = mine_argv
        sys.path[:] = mine_path
        sys.modules.pop("helper", None)
    assert after_argv == mine_argv
    assert after_path == mine_path


# --- Before the hand-off, every failure is this client's ------------------------


def misused(*argv: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run the real command and require a misuse: 64, one sentence, no traceback."""
    finished = instrument(*argv, cwd=cwd)
    assert finished.returncode == exit_codes.EXIT_MISUSE, (
        finished.returncode,
        finished.stdout,
        finished.stderr,
    )
    assert finished.returncode != exit_codes.EXIT_DENY
    assert "Traceback" not in finished.stderr, finished.stderr
    return finished.returncode, finished.stdout, finished.stderr


def a_tree_with_a_quiet_program(root: Path) -> Path:
    tree = root / "tree"
    tree.mkdir()
    (tree / "app.py").write_text("pass\n", encoding="utf-8")
    return tree


def test_a_point_naming_an_absent_attribute_of_a_loaded_module_is_a_misuse(
    tmp_path: Path,
) -> None:
    """`sys` is in every interpreter, so this point is refused before anything runs."""
    pack = plant_pack(
        tmp_path,
        name="absent-point",
        module="sys",
        attribute="no_such_attribute",
        capability="example.action",
    )
    _, _, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "no_such_attribute" in err


def test_an_execution_module_without_a_wrap_is_a_misuse(tmp_path: Path) -> None:
    pack = plant_pack(
        tmp_path,
        name="no-wrap",
        module="subprocess",
        attribute="Popen",
        capability="process.spawn",
        interpose="NOTHING = 1\n",
    )
    _, _, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "wrap" in err
    assert "interpose.py" in err


def test_an_execution_module_that_raises_is_a_misuse(tmp_path: Path) -> None:
    """A pack is code the person running it chose; a pack that will not load is theirs."""
    pack = plant_pack(
        tmp_path,
        name="raising",
        module="subprocess",
        attribute="Popen",
        capability="process.spawn",
        interpose='raise RuntimeError("this pack is broken")\n',
    )
    _, _, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "did not load" in err
    assert "this pack is broken" in err


def test_a_wrapper_factory_that_raises_is_a_misuse(tmp_path: Path) -> None:
    """The factory produced no wrapper, so nothing was installed and nothing ran."""
    pack = plant_pack(
        tmp_path,
        name="bad-factory",
        module="sys",
        attribute="argv",
        capability="example.action",
        interpose=(
            "def wrap(original, capability, boundary):\n"
            '    raise RuntimeError("this factory is broken")\n'
        ),
    )
    _, _, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "could not be made" in err
    assert "this factory is broken" in err


def test_two_packs_claiming_one_point_is_a_misuse(tmp_path: Path) -> None:
    first = plant_spawn_pack(tmp_path, name="first")
    second = plant_spawn_pack(tmp_path, name="second")
    _, _, err = misused(
        "run",
        "--pack",
        str(first),
        "--pack",
        str(second),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "already wrapped" in err
    assert "Popen" in err


def test_a_script_that_is_not_there_is_a_misuse(tmp_path: Path) -> None:
    """A mistyped file name is not a denial, and the daemon is never asked about it."""
    pack = plant_spawn_pack(tmp_path)
    _, _, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "no_such_app.py",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "no_such_app.py" in err
    assert "found no file to run" in err


def test_a_module_form_naming_no_module_is_a_misuse(tmp_path: Path) -> None:
    pack = plant_spawn_pack(tmp_path)
    _, _, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "-m",
        "sayfirst_no_such_module",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "sayfirst_no_such_module" in err
    assert "found no module named" in err


# --- The scope a person typed is the scope on the wire --------------------------


def a_spawning_tree(root: Path) -> Path:
    tree = root / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    return tree


def test_the_scope_named_on_the_command_line_is_the_scope_on_the_wire(
    tmp_path: Path,
) -> None:
    """Measured on the wire: a required option that had no effect is worse than none.

    Before this, `--scope` was validated into the profile and then discarded,
    and every governed effect was decided — and would have been cached — in
    `local`, whatever the operator typed.
    """
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run",
            "--pack",
            str(pack),
            "--socket",
            str(socket_path),
            "--scope",
            "a-scope-that-is-not-local",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert len(asks) == 1, asks
    assert asks[0]["scope"] == "a-scope-that-is-not-local"
    assert asks[0]["capability"] == "process.spawn"


def test_the_default_scope_is_still_sent_as_itself(tmp_path: Path) -> None:
    """The option is required, so `local` on the wire means somebody typed `local`."""
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run",
            "--pack",
            str(pack),
            "--socket",
            str(socket_path),
            "--scope",
            "local",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert [ask["scope"] for ask in asks] == ["local"]


# --- A refusal says which pack to fix -------------------------------------------


def test_the_second_of_two_packs_is_named_when_it_is_the_invalid_one(tmp_path: Path) -> None:
    """The sentence alone does not say which `--pack` to go and fix."""
    first = plant_spawn_pack(tmp_path, name="first")
    second = plant_pack(
        tmp_path,
        name="second",
        module="shutil",
        attribute="rmtree",
        capability="file.remove",
    )
    # An underscore, which the control plane's own ask schema refuses — so the
    # second pack is invalid for a reason no reader has to take on trust, and
    # `nope` would not do: a single bare word is a spelling the schema admits.
    (second / "pack.toml").write_text(
        (second / "pack.toml")
        .read_text(encoding="utf-8")
        .replace('capability = "file.remove"', 'capability = "file_remove"'),
        encoding="utf-8",
    )
    code, out, err = refuse(
        "run",
        "--pack",
        str(first),
        "--pack",
        str(second),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert err.startswith(f"{second}: ")
    assert "capability" in err
    assert str(first) not in err
    assert out == ""


def test_the_pack_is_named_exactly_as_it_was_typed(tmp_path: Path, monkeypatch) -> None:
    """A resolved path is not what the reader has in their shell history."""
    pack = plant_spawn_pack(tmp_path)
    (pack / "pack.toml").write_text("[pack]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code, _, err = refuse(
        "run",
        "--pack",
        "./pack",
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert err.startswith("./pack: ")


def test_a_missing_pack_directory_is_named_once_and_not_twice(tmp_path: Path) -> None:
    """The path prefix and the sentence's own path must not read as two packs."""
    absent = tmp_path / "absent"
    code, _, err = refuse(
        "run",
        "--pack",
        str(absent),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert err.startswith(f"{absent}: ")
    assert "pack.toml" in err


def test_a_package_without_a_main_is_a_misuse_not_a_traceback(tmp_path: Path) -> None:
    """`-m email` names a package with no `__main__`: not a program to run, and not a denial.

    Not `json`, which was the example here until Python 3.14 gave it a `__main__`
    — a package with none, on every interpreter this client supports, is `email`.
    """
    pack = plant_spawn_pack(tmp_path)
    _, _, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "-m",
        "email",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "no `__main__` in the package 'email'" in err
    assert "Traceback" not in err


def test_a_manifest_nested_deeper_than_the_reader_parses_is_a_misuse(tmp_path: Path) -> None:
    """The same refusal `packs check` gives, through the verb that runs a program.

    Measured as the defect: exit 1 with a `RecursionError` traceback, for a pack
    directory the invocation named — one number carrying both « this invocation
    is wrong » and « the control plane answered deny ».
    """
    pack = plant_spawn_pack(tmp_path)
    (pack / "pack.toml").write_text("x = " + "[" * 3000 + "]" * 3000 + "\n", encoding="utf-8")
    code, _, err = refuse(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert "nests deeper than this reader parses" in err


def test_a_pack_naming_an_absent_attribute_on_a_later_import_is_a_misuse_not_a_traceback(
    tmp_path: Path,
) -> None:
    """The one break left in « 1 is never this client's ».

    `EngineMisuse` is raised inside the program's own import — the one check
    the engine cannot make sooner, because until that module has run the
    attribute does not exist to be absent — and `commands._run` caught
    `LaunchMisuse` and `SocketClientProblem` only. So the pack's mistake reached
    a shell as exit 1, this client's published code for « deny », with a
    traceback naming the engine. It is the byte-identical shape of a `-m` name
    that resolves to a package with no `__main__`, which is already 64, and the
    reason is the same word for word: the pack is the invocation's, the program
    is innocent, and no question was ever put.

    The module is one the program imports and the launcher's own work does not,
    so the point is still waiting when the program reaches it. A module already
    loaded is refused before anything runs, which is the test above this one.
    """
    pack = plant_pack(
        tmp_path,
        name="absent-on-import",
        module="sqlite3",
        attribute="nosuchattr",
        capability="database.open",
    )
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text("print('the program started')\nimport sqlite3\n", encoding="utf-8")
    _, out, err = misused(
        "run",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
        cwd=tree,
    )
    assert "has no nosuchattr" in err
    assert "Traceback" not in err
    # Anti-vacuity: the refusal has to come from INSIDE the program's import,
    # which only a program that got as far as printing can show. A module the
    # launcher's own work had loaded would be refused before the hand-off, on
    # the clause the test above this one covers, and this one would pass while
    # proving nothing about the clause it is named for.
    assert out == "the program started\n", "the program never ran, so this is the other clause"


# -- an outcome the program does not handle ends with the status this client publishes


def _run_under(tmp_path: Path, app: str, socket_path: Path) -> object:
    tree = tmp_path / "tree"
    tree.mkdir(exist_ok=True)
    (tree / "app.py").write_text(app, encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    return instrument(
        "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
        "--", "app.py", cwd=tree,
    )  # fmt: skip


def test_a_suspension_the_program_does_not_handle_ends_with_the_suspend_status(
    tmp_path: Path,
) -> None:
    """5, as `ask` says it — not the interpreter's 1, which is this client's « deny »."""
    stub = Stub("review_approve")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = _run_under(tmp_path, SPAWNING_APP, socket_path)
    assert finished.returncode == exit_codes.EXIT_SUSPEND, finished.stderr
    assert "Suspended" in finished.stderr and "Traceback" in finished.stderr


def test_a_control_plane_that_could_not_be_asked_is_not_a_denial(tmp_path: Path) -> None:
    """Article 1: « could not ask » and « denied » never read as each other, in `$?` either."""
    finished = _run_under(tmp_path, SPAWNING_APP, tmp_path / "absent.sock")
    assert finished.returncode == exit_codes.EXIT_COULD_NOT_ASK, finished.stderr
    assert "CouldNotAsk" in finished.stderr


def test_an_unavailable_policy_is_could_not_ask_too(tmp_path: Path) -> None:
    stub = Stub("policy_unavailable_is_could_not_ask")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = _run_under(tmp_path, SPAWNING_APP, socket_path)
    assert finished.returncode == exit_codes.EXIT_COULD_NOT_ASK, finished.stderr


def test_an_outcome_the_program_handles_is_the_programs_own_ending(tmp_path: Path) -> None:
    handled = (
        "import subprocess, sys\n"
        "from sayfirst_boundary import Denied\n"
        "try:\n"
        '    subprocess.run(["true"], check=True)\n'
        "except Denied:\n"
        '    print("handled the denial")\n'
        "    sys.exit(0)\n"
    )
    stub = Stub("deny")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = _run_under(tmp_path, handled, socket_path)
    assert finished.returncode == 0, finished.stderr
    assert "handled the denial" in finished.stdout


def test_every_boundary_outcome_has_its_published_status() -> None:
    from sayfirst_boundary import AskRefused, CouldNotAsk, Denied, Suspended

    assert commands.ending_for(Denied(decision_ref="d", capability="c", reason="r")) == 1
    assert commands.ending_for(Suspended(approval_ref="a", decision_ref="d", capability="c")) == 5
    assert commands.ending_for(AskRefused(problem_code="p", detail="d")) == 3
    assert commands.ending_for(CouldNotAsk(detail="d", retryable=None)) == 4
    assert commands.ending_for(RuntimeError("the program's own")) is None
