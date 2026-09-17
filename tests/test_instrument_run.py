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

import io
import os
from pathlib import Path

import pytest
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
from sayfirst_cli.instrument import commands


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
    """`-m json` names a package with no `__main__`: not a program to run, and not a denial."""
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
        "json",
        cwd=a_tree_with_a_quiet_program(tmp_path),
    )
    assert "no `__main__` in the package 'json'" in err
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
