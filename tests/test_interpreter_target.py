# SPDX-License-Identifier: Apache-2.0
"""`-- python app.py`: the program runs under the interpreter a person named.

A governed program runs inside the interpreter that carries this command. That
is right when the two are one environment, and it is a quiet lie the moment they
are not: installed as a tool of its own, this command's interpreter has none of
an application's dependencies, so a target spelled `python app.py` — the way
the person runs it every day — would either be refused, or, worse, be run by an
interpreter they did not name and fail on its first import.

So the first word of a target may name an interpreter, and then the WHOLE
command is handed to that interpreter: same verb, same packs, same profile, the
word removed. The boundary is installed in that process before the program's
first import, exactly as it is in this one; the three distributions that make
the boundary are lent to it by location, and nothing else of this environment
is.

These cases use a second environment that holds one module this one does not,
because « it ran under the named interpreter » has to be something a program
can only do there.
"""

from __future__ import annotations

import io
import os
import sys
import sysconfig
import venv
from pathlib import Path

import pytest
from governed_programs import instrument, plain_environment, plant_spawn_pack
from sayfirst_contract_stub.stub import Stub
from sayfirst_contract_stub.stub_http import serve

from sayfirst_cli import exit_codes
from sayfirst_cli.instrument import commands, interpreter

#: A program only the second environment can run, which then makes one named
#: effect and says which interpreter it ran under and what it was handed.
APP = """\
import importlib.util
import subprocess
import sys

import only_in_the_application

subprocess.run(["true"], check=True)
print("lent", importlib.util.find_spec("pytest") is not None)
print("prefix", sys.prefix)
print("argv", sys.argv)
print("head", sys.path[0])
print("found", only_in_the_application.WHERE)
"""


@pytest.fixture(scope="module")
def application(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A second environment, of this same Python, holding one module of its own."""
    root = tmp_path_factory.mktemp("application") / "env"
    venv.create(root, with_pip=False, symlinks=True)
    purelib = Path(sysconfig.get_path("purelib", vars={"base": str(root), "platbase": str(root)}))
    (purelib / "only_in_the_application.py").write_text('WHERE = "application"\n', "utf-8")
    assert (root / "bin" / "python").exists()
    return root


def _tree(tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(APP, encoding="utf-8")
    return tree


@pytest.mark.parametrize(
    ("target", "named"),
    [
        (["python", "app.py"], "python"),
        (["python3", "-m", "pkg"], "python3"),
        (["python3.13", "app.py"], "python3.13"),
        (["/usr/bin/python3", "app.py"], "/usr/bin/python3"),
        (["./env/bin/python", "app.py"], "./env/bin/python"),
        (["app.py"], None),
        (["-m", "pkg"], None),
        (["python.py"], None),
        (["pythonic"], None),
        (["tools/python-report.py"], None),
        ([], None),
    ],
)
def test_an_interpreter_is_recognised_by_the_spelling_of_the_first_word(
    target: list[str], named: str | None
) -> None:
    assert interpreter.named_in(target) == named


def test_the_program_runs_under_the_interpreter_that_was_named(
    application: Path, tmp_path: Path
) -> None:
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--", str(application / "bin" / "python"), "app.py", "--flag", "value",
            cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    said = dict(line.split(" ", 1) for line in finished.stdout.splitlines())
    assert said["found"] == "application"
    assert Path(said["prefix"]) == application
    # `pytest` is installed beside this command and not in the application's
    # environment, and it stays that way: what is lent is three packages by
    # name, never the directory they happen to be installed in.
    assert said["lent"] == "False"
    # What the interpreter would have handed the program for `python app.py …`:
    # its own arguments, and its own directory at the head of the import path.
    assert said["argv"] == "['app.py', '--flag', 'value']"
    assert Path(said["head"]) == tree
    # …and it was governed there: the named effect was asked about, once.
    assert stub.decision_count == 1


def test_a_bare_interpreter_name_is_looked_up_the_way_a_shell_would(
    application: Path, tmp_path: Path
) -> None:
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    environment = plain_environment()
    environment["PATH"] = f"{application / 'bin'}{os.pathsep}{environment.get('PATH', '')}"
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--", "python", "app.py", cwd=tree, env=environment,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert "found application" in finished.stdout
    assert stub.decision_count == 1


def test_without_the_word_the_program_runs_in_this_commands_own_interpreter(
    application: Path, tmp_path: Path
) -> None:
    """The difference the word makes, so the case above is not vacuous."""
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope", "local",
        "--", "app.py", cwd=tree,
    )  # fmt: skip
    assert finished.returncode == 1
    assert "No module named 'only_in_the_application'" in finished.stderr


def test_a_denial_under_a_named_interpreter_stops_the_effect_there_too(
    application: Path, tmp_path: Path
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    marker = tree / "ran"
    (tree / "app.py").write_text(
        f'import subprocess\n\nsubprocess.run(["touch", {str(marker)!r}], check=True)\n',
        encoding="utf-8",
    )
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("deny")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--", str(application / "bin" / "python"), "app.py", cwd=tree,
        )  # fmt: skip
    assert stub.decision_count == 1
    assert not marker.exists()
    assert finished.returncode == 1
    assert "Denied" in finished.stderr


def test_the_programs_own_exit_code_comes_back_from_the_named_interpreter(
    application: Path, tmp_path: Path
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text("import sys\n\nsys.exit(3)\n", encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope", "local",
        "--", str(application / "bin" / "python"), "app.py", cwd=tree,
    )  # fmt: skip
    assert finished.returncode == 3, finished.stderr


def test_a_verification_runs_under_the_named_interpreter_as_well(
    application: Path, tmp_path: Path
) -> None:
    """The harness is a process of its own, so it has to be lent the same three."""
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "verify", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"),
        "--scope", "local", "--", str(application / "bin" / "python"), "app.py", cwd=tree,
    )  # fmt: skip
    # Nobody is listening, so nothing is concluded — but it is the HARNESS that
    # says so, from inside the named interpreter, which is the point: before
    # the three were lent to it, it ended on an import error and said nothing.
    assert finished.returncode == exit_codes.EXIT_COULD_NOT_ASK, finished.stderr
    assert "the chain could not be read" in finished.stderr
    assert "No module named" not in finished.stderr


def test_a_name_that_finds_no_interpreter_is_a_misuse(tmp_path: Path) -> None:
    out, err = io.StringIO(), io.StringIO()
    pack = plant_spawn_pack(tmp_path)
    code = commands.main(
        ["run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope",
         "local", "--", str(tmp_path / "bin" / "python3"), "app.py"],
        out=out, err=err,
    )  # fmt: skip
    assert code == exit_codes.EXIT_MISUSE
    assert "python3" in err.getvalue() and "interpreter" in err.getvalue()


def test_an_interpreter_too_old_to_hold_the_boundary_is_refused_before_it_is_handed_anything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused by THIS process, in words, rather than left to fail on syntax there."""
    monkeypatch.setattr(interpreter, "MINIMUM", (sys.version_info[0], sys.version_info[1] + 1))
    handed: list[object] = []
    with pytest.raises(interpreter.launch.LaunchMisuse, match="or later"):
        interpreter.hand_the_command_to(
            sys.executable, ["instrument", "run"], execv=lambda *a: handed.append(a)
        )
    assert handed == []


def test_this_commands_own_interpreter_is_not_handed_anything(tmp_path: Path) -> None:
    """Naming the interpreter already running is the in-process path, word removed."""
    assert interpreter.is_this_one(sys.executable)
    assert not interpreter.is_this_one("/somewhere/else/bin/python")


def test_what_is_lent_is_three_packages_and_their_metadata_and_nothing_else() -> None:
    lent = interpreter.lent_locations()
    assert set(lent) == {"packages", "distributions"}
    assert set(lent["packages"]) == {"sayfirst_cli", "sayfirst_boundary", "sayfirst_contract"}
    assert set(lent["distributions"]) == {"sayfirst-cli", "sayfirst-boundary", "sayfirst-contract"}
    for name, where in lent["packages"].items():
        assert (Path(where) / name / "__init__.py").is_file(), (name, where)
    for name, where in lent["distributions"].items():
        assert list(Path(where).glob(f"{name.replace('-', '_')}-*.dist-info")), (name, where)


def test_the_floor_is_the_one_this_distribution_declares() -> None:
    """Two copies of one number, held together: a process cannot read `pyproject.toml`
    from an installed wheel, and the project file cannot import a module."""
    import re
    import tomllib

    declared = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["requires-python"]
    floor = re.search(r">=\s*(\d+)\.(\d+)", declared)
    assert floor is not None, declared
    assert (int(floor[1]), int(floor[2])) == interpreter.MINIMUM


# -- C4: console-script agents (a shebang) and refused runners --------------------


def test_a_runner_in_the_first_position_is_refused_with_the_way_that_works(
    tmp_path: Path,
) -> None:
    for runner in ("uv", "poetry", "pdm", "pipenv"):
        with pytest.raises(interpreter.launch.LaunchMisuse) as refusal:
            interpreter.selection([runner, "run", "app.py"])
        said = str(refusal.value)
        assert runner in said and "which python" in said
    # `uv` not followed by `run` is not a runner invocation and is left alone
    # (it would be an executable named `uv`, which is not a shebang Python).
    assert interpreter.selection(["uv", "--version"]) is None


def test_an_executable_script_hands_over_by_its_shebang(application: Path, tmp_path: Path) -> None:
    agent = tmp_path / "myagent"
    agent.write_text(f"#!{application / 'bin' / 'python'}\n{APP}", encoding="utf-8")
    agent.chmod(0o755)
    chosen = interpreter.selection([str(agent), "--flag"])
    assert chosen is not None
    executable, program = chosen
    # The shebang path is kept as written (the venv's python), not realpath-
    # resolved, because that interpreter is what sets up the venv.
    assert Path(executable) == application / "bin" / "python"
    # The script itself is the program that interpreter runs, argv[0] included.
    assert program == [str(agent), "--flag"]


def test_a_shebang_using_env_is_read(application: Path, tmp_path: Path) -> None:
    agent = tmp_path / "myagent"
    agent.write_text("#!/usr/bin/env python3\nprint('x')\n", encoding="utf-8")
    agent.chmod(0o755)
    chosen = interpreter.selection([str(agent)])
    assert chosen is not None
    # `env python3` is resolved on PATH the way a shell would, and handed over
    # as that path (which need not be this test's own interpreter).
    import shutil

    assert chosen[0] == os.path.abspath(shutil.which("python3"))
    assert chosen[1] == [str(agent)]


def test_a_non_executable_script_is_left_in_process_whatever_its_shebang(
    application: Path, tmp_path: Path
) -> None:
    agent = tmp_path / "app.py"
    agent.write_text(f"#!{application / 'bin' / 'python'}\nprint('x')\n", encoding="utf-8")
    # Not executable: a shebang only matters for a file the kernel would run.
    assert interpreter.selection([str(agent)]) is None


def test_a_shebang_that_is_not_a_python_is_left_alone(tmp_path: Path) -> None:
    for line in ("#!/bin/sh\n", "#!/usr/bin/env -S uv run python\n", "#!/usr/bin/env bash\n"):
        script = tmp_path / "s"
        script.write_text(line + "true\n", encoding="utf-8")
        script.chmod(0o755)
        assert interpreter.shebang_interpreter(str(script)) is None
        assert interpreter.selection([str(script)]) is None


def test_the_console_script_agent_runs_under_its_own_interpreter(
    application: Path, tmp_path: Path
) -> None:
    """The whole point: an agent started as an executable, not as `python …`, is
    governed inside the interpreter its shebang names and keeps its dependencies."""
    tree = tmp_path / "tree"
    tree.mkdir()
    agent = tree / "myagent"
    agent.write_text(f"#!{application / 'bin' / 'python'}\n{APP}", encoding="utf-8")
    agent.chmod(0o755)
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--", "./myagent", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert "found application" in finished.stdout
    assert stub.decision_count == 1


def test_a_refused_runner_governs_nothing_and_says_the_fix(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text('print("ran")\n', encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope", "local",
        "--", "uv", "run", "app.py", cwd=tree,
    )  # fmt: skip
    assert finished.returncode == exit_codes.EXIT_MISUSE
    assert "cannot govern a program started by 'uv'" in finished.stderr
    assert "ran" not in finished.stdout


# -- review findings: re-exec must not re-select; the probe ignores startup ------


def test_a_handed_over_command_does_not_choose_the_interpreter_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mark a hand-off sets makes the second `sayfirst instrument` run its
    target in place, without reading its first word again."""
    monkeypatch.setenv(interpreter.CHOSEN_VARIABLE, "1")
    # An arbitrary namespace with a target that WOULD otherwise be selected
    # (a `python` word): with the mark set, selection is skipped and the target
    # is left for the in-process run, and the mark is consumed.
    parser = commands.build_parser()
    ns = parser.parse_args(["run", "--pack", "subprocess", "--scope", "local", "--", "python", "x"])
    commands._to_the_interpreter_the_target_names(parser, ns)
    assert ns.target == ["python", "x"]  # untouched: no re-selection
    assert interpreter.CHOSEN_VARIABLE not in os.environ  # consumed


def test_an_executable_whose_shebang_names_a_third_interpreter_is_not_re_followed(
    application: Path, tmp_path: Path
) -> None:
    """Named interpreter A, program's shebang B: the program runs under A, the one
    named, not B. Before the fix the handed-over process read the shebang again and
    exec'd into B, running the program under the wrong environment."""
    tree = tmp_path / "tree"
    tree.mkdir()
    # The program is executable and its shebang names THIS test's interpreter,
    # which does not have `only_in_the_application`; the named interpreter
    # (`application`) does. If the program ran under the shebang's interpreter it
    # would fail to import it.
    agent = tree / "agent"
    agent.write_text(f"#!{sys.executable}\n{APP}", encoding="utf-8")
    agent.chmod(0o755)
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--", str(application / "bin" / "python"), "agent", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    said = dict(line.split(" ", 1) for line in finished.stdout.splitlines())
    assert said["found"] == "application", finished.stdout
    assert Path(said["prefix"]) == application


def test_the_version_probe_ignores_a_targets_startup_output(tmp_path: Path) -> None:
    """A target whose sitecustomize announces itself on startup is a usable
    interpreter, not a malformed version: the probe runs isolated and reads its
    own marked line."""
    import sysconfig
    import venv

    root = tmp_path / "noisy"
    venv.create(root, with_pip=False, symlinks=True)
    purelib = Path(sysconfig.get_path("purelib", vars={"base": str(root), "platbase": str(root)}))
    (purelib / "sitecustomize.py").write_text("print('environment ready')\n", "utf-8")
    # -I in the probe suppresses site/sitecustomize, so the answer is clean.
    assert interpreter.version_of(str(root / "bin" / "python")) == sys.version_info[:2]


# -- review findings: a missing shebang interpreter, the ceiling, followed children, safe path --


def test_a_shebang_naming_a_python_that_is_not_there_is_a_misuse(tmp_path: Path) -> None:
    """The kernel refuses such a script (status 127); running it under this command's
    own interpreter instead is the dishonest reading the module refuses by name."""
    for line in ("#!/usr/bin/env python3.99\n", f"#!{tmp_path / 'gone' / 'python3'}\n"):
        script = tmp_path / "agent"
        script.write_text(line + "print('ran')\n", encoding="utf-8")
        script.chmod(0o755)
        with pytest.raises(interpreter.launch.LaunchMisuse, match="no such interpreter"):
            interpreter.selection([str(script)])


def test_the_command_refuses_a_script_whose_python_is_missing(tmp_path: Path) -> None:
    marker = tmp_path / "ran"
    script = tmp_path / "agent"
    script.write_text(
        f"#!/usr/bin/env python3.99\nopen({str(marker)!r}, 'w').close()\n", encoding="utf-8"
    )
    script.chmod(0o755)
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope",
        "local", "--", str(script), cwd=tmp_path,
    )  # fmt: skip
    assert finished.returncode == exit_codes.EXIT_MISUSE, finished.stderr
    assert "python3.99" in finished.stderr
    assert "Traceback" not in finished.stderr
    assert not marker.exists()


def test_the_ceiling_is_the_one_this_distribution_declares() -> None:
    """The lent packages declare `<3.15`; the copy a running process reads is held to it."""
    import re
    import tomllib

    declared = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["requires-python"]
    ceiling = re.search(r"<\s*(\d+)\.(\d+)", declared)
    assert ceiling is not None, declared
    assert (int(ceiling[1]), int(ceiling[2])) == interpreter.BEYOND


def test_an_interpreter_too_new_for_the_lent_packages_is_refused_before_it_is_handed_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(interpreter, "BEYOND", (sys.version_info[0], sys.version_info[1]))
    handed: list[object] = []
    with pytest.raises(interpreter.launch.LaunchMisuse, match="before"):
        interpreter.hand_the_command_to(
            sys.executable, ["instrument", "run"], execv=lambda *a: handed.append(a)
        )
    assert handed == []


def test_following_children_under_an_interpreter_without_this_client_is_refused(
    application: Path, tmp_path: Path
) -> None:
    """The packages are lent to ONE process; a child is a fresh one with nothing lent,
    so every Python child would die at start-up. Refused before anything runs."""
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope",
        "local", "--follow-children", "--", str(application / "bin" / "python"), "app.py",
        cwd=tree,
    )  # fmt: skip
    assert finished.returncode == exit_codes.EXIT_MISUSE, (finished.stdout, finished.stderr)
    assert "--follow-children" in finished.stderr
    assert "found application" not in finished.stdout


@pytest.fixture(scope="module")
def application_with_this_client(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A second environment that can import this client on its own, as an install would."""
    root = tmp_path_factory.mktemp("installed") / "env"
    venv.create(root, with_pip=False, symlinks=True)
    purelib = Path(sysconfig.get_path("purelib", vars={"base": str(root), "platbase": str(root)}))
    (purelib / "only_in_the_application.py").write_text('WHERE = "application"\n', "utf-8")
    locations = sorted(set(interpreter.lent_locations()["packages"].values()))
    (purelib / "this_client.pth").write_text("\n".join(locations) + "\n", "utf-8")
    return root


def test_following_children_under_an_interpreter_with_this_client_is_handed_over(
    application_with_this_client: Path, tmp_path: Path
) -> None:
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock"):
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(tmp_path / "d.sock"), "--scope",
            "local", "--follow-children", "--",
            str(application_with_this_client / "bin" / "python"), "app.py",
            cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "found application" in finished.stdout


SAFE_PATH_APP = """\
import sys

import mylib

print("head", sys.path[0])
print("found", mylib.WHERE)
"""


def _a_safe_path_tree(tmp_path: Path) -> tuple[Path, Path]:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SAFE_PATH_APP, encoding="utf-8")
    libs = tmp_path / "libs"
    libs.mkdir()
    (libs / "mylib.py").write_text('WHERE = "libs"\n', encoding="utf-8")
    return tree, libs


def test_a_safe_path_keeps_the_import_path_the_interpreter_gave_the_program(
    tmp_path: Path,
) -> None:
    """`PYTHONSAFEPATH` keeps the script's directory off the path, so the head is the
    person's own first entry; the launcher replaced it and the program's import failed."""
    import subprocess

    tree, libs = _a_safe_path_tree(tmp_path)
    environment = {**os.environ, "PYTHONSAFEPATH": "1", "PYTHONPATH": str(libs)}
    plain = subprocess.run(
        [sys.executable, "app.py"], cwd=tree, env=environment, capture_output=True, text=True,
        check=False,
    )  # fmt: skip
    assert plain.returncode == 0, plain.stderr
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope",
        "local", "--", "app.py", cwd=tree, env=environment,
    )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == plain.stdout


def test_a_safe_path_is_kept_under_a_named_interpreter_too(
    application: Path, tmp_path: Path
) -> None:
    """The hand-over starts that interpreter with `-P` of its own; the person's setting
    is read off the environment, and the program gets the path it would have had."""
    import subprocess

    tree, libs = _a_safe_path_tree(tmp_path)
    environment = {**os.environ, "PYTHONSAFEPATH": "1", "PYTHONPATH": str(libs)}
    plain = subprocess.run(
        [str(application / "bin" / "python"), "app.py"], cwd=tree, env=environment,
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert plain.returncode == 0, plain.stderr
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--socket", str(tmp_path / "absent.sock"), "--scope",
        "local", "--", str(application / "bin" / "python"), "app.py", cwd=tree,
        env=environment,
    )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == plain.stdout
