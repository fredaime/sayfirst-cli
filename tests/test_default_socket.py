# SPDX-License-Identifier: Apache-2.0
"""A per-user profile that names no socket is looked for at the per-user default.

The rule is the contract's, read and never restated: a per-user daemon given no
address binds `default_socket_path`, and this client given no `--socket` looks
at the same function's answer, so neither is told where the other is. Three
things are held here because they are what a default could quietly break.

* **An explicit `--socket` is still the address.** A default that outranked
  what a person typed would ask a daemon they did not name.
* **Nothing is searched for.** One name is computed from the environment; a
  daemon serving anywhere else is not found, and that is « could not ask »
  (exit 4) — never a denial, and never permission (articles 1 and 2).
* **An address nobody typed is said when it fails**, because a reader cannot
  act on « unreachable » at a path they never saw.

A system profile gets no default: it already has to say which account the
daemon runs as, and where is the other half of the same sentence.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from governed_programs import SPAWNING_APP, instrument, plain_environment, plant_spawn_pack
from sayfirst_contract_stub.stub import Stub
from sayfirst_contract_stub.stub_http import serve

from sayfirst_cli import approvals, ask, exit_codes


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A home directory with no runtime directory, short enough to hold an address.

    Made directly under the system's temporary directory rather than under
    `tmp_path`: a local address has about a hundred bytes, and the runner's own
    directory for a test spends most of them before the default rule has added
    its four levels.
    """
    directory = Path(tempfile.mkdtemp(prefix="sf", dir="/tmp"))
    monkeypatch.setenv("HOME", str(directory))
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def default_address(home: Path) -> Path:
    address = home / ".sayfirst" / "run" / "daemon.sock"
    address.parent.mkdir(parents=True, exist_ok=True)
    return address


def asked(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    return ask.main(list(argv), out=out, err=err), out.getvalue(), err.getvalue()


def test_ask_given_no_socket_asks_the_daemon_at_the_per_user_default(home: Path) -> None:
    stub = Stub("allow")
    with serve(stub, default_address(home)):
        code, out, err = asked("--capability", "example.read", "--scope", "local")
    assert code == exit_codes.EXIT_ALLOW, err
    assert "outcome: allow" in out
    assert stub.decision_count == 1


def test_a_socket_somebody_named_is_the_one_that_is_asked(home: Path, tmp_path: Path) -> None:
    at_the_default, named = Stub("deny"), Stub("allow")
    with serve(at_the_default, default_address(home)), serve(named, home / "own.sock") as own:
        code, out, _ = asked("--capability", "example.read", "--socket", str(own))
    assert code == exit_codes.EXIT_ALLOW
    assert (named.decision_count, at_the_default.decision_count) == (1, 0)


def test_nobody_at_the_default_is_could_not_ask_and_says_where_it_looked(home: Path) -> None:
    code, out, err = asked("--capability", "example.read")
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert out == ""
    assert f"socket: {home}/.sayfirst/run/daemon.sock (the per-user default" in err
    assert "could not ask: unreachable" in err


def test_the_envelope_is_still_the_only_thing_on_the_stream_under_json(home: Path) -> None:
    code, _, err = asked("--capability", "example.read", "--json")
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert json.loads(err)["problem"]["code"] == "unreachable"


def test_a_socket_somebody_named_is_not_announced_as_a_default(home: Path) -> None:
    code, _, err = asked("--capability", "example.read", "--socket", str(home / "absent.sock"))
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert "per-user default" not in err


def test_a_daemon_serving_somewhere_else_is_not_gone_looking_for(home: Path) -> None:
    elsewhere = Stub("allow")
    with serve(elsewhere, home / "elsewhere.sock"):
        code, _, _ = asked("--capability", "example.read")
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert elsewhere.decision_count == 0


def test_a_system_profile_is_never_given_a_default_address(home: Path) -> None:
    code, out, err = asked(
        "--capability", "example.read", "--mode", "system", "--daemon-user", "root"
    )
    assert code == exit_codes.EXIT_MISUSE
    assert "--socket is required in system mode" in err


def test_the_reads_look_at_the_same_default(home: Path) -> None:
    """One helper opens every read's connection, so one read stands for them."""
    out, err = io.StringIO(), io.StringIO()
    code = approvals.main(
        ["show", "--approval", "0d2f7a52-8f0e-4c55-9f59-0e4f6f3f7c11", "--scope", "local"],
        out=out,
        err=err,
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert f"socket: {home}/.sayfirst/run/daemon.sock (the per-user default" in err.getvalue()


def _environment(home: Path) -> dict[str, str]:
    environment = plain_environment()
    environment.pop("XDG_RUNTIME_DIR", None)
    environment["HOME"] = str(home)
    return environment


def test_a_governed_program_given_no_socket_is_asked_about_at_the_default(
    home: Path, tmp_path: Path
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    stub = Stub("allow")
    with serve(stub, default_address(home)):
        finished = instrument(
            "run", "--pack", str(pack), "--scope", "local", "--", "app.py",
            cwd=tree, env=_environment(home),
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert stub.decision_count == 1


def test_a_governed_effect_with_nobody_at_the_default_fails_closed(
    home: Path, tmp_path: Path
) -> None:
    """The effect does not happen, the run ends « could not ask », and the
    address nobody typed is on the error stream before the program starts.

    The program does not handle the outcome, so the traceback is still its
    own; the status is this client's, because the interpreter's `1` is this
    client's « deny » and nobody was there to deny anything."""
    tree = tmp_path / "tree"
    tree.mkdir()
    marker = tree / "ran"
    (tree / "app.py").write_text(
        f'import subprocess\n\nsubprocess.run(["touch", {str(marker)!r}], check=True)\n',
        encoding="utf-8",
    )
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--scope", "local", "--", "app.py",
        cwd=tree, env=_environment(home),
    )  # fmt: skip
    assert not marker.exists()
    assert finished.returncode == exit_codes.EXIT_COULD_NOT_ASK
    assert "CouldNotAsk" in finished.stderr
    assert f"socket: {home}/.sayfirst/run/daemon.sock (the per-user default" in finished.stderr


def test_a_program_that_asks_nothing_still_runs_with_nobody_there(
    home: Path, tmp_path: Path
) -> None:
    """The default changes where a question goes, never whether a program runs."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text('print("quiet")\n', encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "run", "--pack", str(pack), "--scope", "local", "--", "app.py",
        cwd=tree, env=_environment(home),
    )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == "quiet\n"


def test_a_verification_with_nobody_at_the_default_concludes_nothing_and_says_where(
    home: Path, tmp_path: Path
) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    pack = plant_spawn_pack(tmp_path)
    finished = instrument(
        "verify", "--pack", str(pack), "--scope", "local", "--", "app.py",
        cwd=tree, env=_environment(home),
    )  # fmt: skip
    assert finished.returncode == exit_codes.EXIT_COULD_NOT_ASK, finished.stderr
    assert f"socket: {home}/.sayfirst/run/daemon.sock (the per-user default" in finished.stderr
