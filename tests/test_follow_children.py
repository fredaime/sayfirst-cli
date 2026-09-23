# SPDX-License-Identifier: Apache-2.0
"""`instrument run --follow-children`: a governed program's Python children govern too.

The engine installs the boundary in one process. A program that spawns another
Python — a worker, a step, a tool — starts a fresh interpreter the boundary is
not in, and its effects reach the world unasked. `--follow-children` puts the
same boundary in every Python child, before the child's code runs, by a
`sitecustomize` on its import path (`follow.py`). These cases read the wire: a
child that makes an effect is one more ask at the daemon when children are
followed, and none when they are not.

The children here are `sys.executable -c …`, run in the interpreter these tests
run in, which has this client installed — the condition `--follow-children`
needs and `follow.py` states. A child that cannot install the boundary raises
out of `sitecustomize` and never runs ungoverned; that is the last case.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from governed_programs import instrument, plant_spawn_pack, recording_daemon

from sayfirst_cli.instrument import commands, follow, manifest

#: A program that spawns a Python child which itself spawns a process. The
#: parent's spawn is governed by the engine in the parent; the child's spawn is
#: governed only if the child installed the boundary too.
PARENT = """\
import subprocess
import sys

subprocess.run(
    [sys.executable, "-c", "import subprocess; subprocess.run(['true'], check=True)"],
    check=True,
)
print("parent done")
"""


def _tree(tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(PARENT, encoding="utf-8")
    return tree


def _asks_for(asks: list[dict[str, object]], capability: str) -> int:
    return sum(1 for ask in asks if ask.get("capability") == capability)


def test_the_child_is_ungoverned_without_the_flag(tmp_path: Path) -> None:
    """The measurement the flag changes: the child's spawn asks nothing on its own."""
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert "parent done" in finished.stdout
    # Only the parent's spawn of the child was asked about.
    assert _asks_for(asks, "process.spawn") == 1


def test_a_followed_child_governs_its_own_effect(tmp_path: Path) -> None:
    """With the flag, the child installs the boundary and asks before it spawns."""
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--follow-children", "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert "parent done" in finished.stdout
    # The parent's spawn of the child, and the child's own spawn: two asks.
    assert _asks_for(asks, "process.spawn") == 2


def test_a_grandchild_is_followed_too(tmp_path: Path) -> None:
    """The environment is left in place, so a child of a child installs it as well."""
    tree = tmp_path / "tree"
    tree.mkdir()
    grandchild = "import subprocess; subprocess.run(['true'], check=True)"
    child = (
        f"import subprocess, sys; "
        f"subprocess.run([sys.executable, '-c', {grandchild!r}], check=True)"
    )
    (tree / "app.py").write_text(
        f"import subprocess, sys\nsubprocess.run([sys.executable, '-c', {child!r}], check=True)\n",
        encoding="utf-8",
    )
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--follow-children", "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    # Parent spawns child, child spawns grandchild, grandchild spawns `true`: three.
    assert _asks_for(asks, "process.spawn") == 3


def _child_environment(config: str) -> dict[str, str]:
    import os

    return {
        **dict(os.environ),
        "PYTHONPATH": f"{follow.bootstrap_path()}:{Path(__file__).resolve().parents[1] / 'src'}",
        follow.CONFIG_VARIABLE: config,
    }


def test_a_followed_childs_effect_fails_closed_when_the_daemon_is_absent(tmp_path: Path) -> None:
    """The boundary installs (a connection is opened at the ask, not before), and the
    effect then fails closed at the absent daemon — never made, never ungoverned."""
    import subprocess
    import sys

    pack = plant_spawn_pack(tmp_path)
    config = follow.configuration(
        [manifest.read_pack(pack)],
        socket=str(tmp_path / "absent.sock"),
        scope="local",
        mode="per_user",
        daemon_user=None,
        principal=None,
    )
    child = tmp_path / "child.py"
    marker = tmp_path / "ran"
    child.write_text(f"import subprocess\nsubprocess.run(['touch', {str(marker)!r}])\n", "utf-8")
    finished = subprocess.run(
        [sys.executable, str(child)],
        env=_child_environment(config),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert finished.returncode != 0
    assert "could not ask" in finished.stderr
    assert not marker.exists(), "the child made its effect despite the daemon being absent"


def test_a_followed_child_that_cannot_install_the_boundary_never_runs(tmp_path: Path) -> None:
    """A configuration naming a pack that will not read: sitecustomize raises before
    the child's program runs, so nothing of it executes."""
    import subprocess
    import sys

    # A configuration whose pack directory holds no manifest: the child's
    # `read_pack` refuses it, and sitecustomize turns that into a SystemExit.
    config = json.dumps(
        {
            "packs": [str(tmp_path / "not-a-pack")],
            "socket": "/s.sock",
            "scope": "local",
            "mode": "per_user",
            "daemon_user": None,
            "principal": None,
        }
    )
    child = tmp_path / "child.py"
    marker = tmp_path / "ran"
    child.write_text(f"open({str(marker)!r}, 'w').close()\n", "utf-8")
    finished = subprocess.run(
        [sys.executable, str(child)],
        env=_child_environment(config),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert finished.returncode != 0
    assert "could not install the boundary" in finished.stderr
    assert not marker.exists(), "the child ran despite the boundary not installing"


def test_verify_does_not_offer_follow_children() -> None:
    """The flag is run's: verify proves one process, and a spawned child is one it
    cannot see (`harness.py`), so following would govern what the proof misses."""
    # argparse refuses an unknown option by raising SystemExit(2); the flag is on
    # `run`'s parser, not `verify`'s.
    with pytest.raises(SystemExit) as refusal:
        commands.main(
            [
                "verify",
                "--pack",
                "subprocess",
                "--scope",
                "local",
                "--follow-children",
                "--",
                "app.py",
            ],
            out=io.StringIO(),
            err=io.StringIO(),
        )
    assert refusal.value.code == 2


def test_the_configuration_carries_what_a_child_rebuilds_the_run_from(tmp_path: Path) -> None:
    pack = plant_spawn_pack(tmp_path)
    config = json.loads(
        follow.configuration(
            [manifest.read_pack(pack)],
            socket="/s.sock",
            scope="local",
            mode="per_user",
            daemon_user=None,
            principal="user:someone",
        )
    )
    assert config == {
        "packs": [str(pack)],
        "socket": "/s.sock",
        "scope": "local",
        "mode": "per_user",
        "daemon_user": None,
        "principal": "user:someone",
    }


def test_the_environment_puts_the_bootstrap_first_and_keeps_what_was_there(tmp_path: Path) -> None:
    pack = plant_spawn_pack(tmp_path)
    env = follow.environment_for(
        {"PYTHONPATH": "/existing", "PYTHONSAFEPATH": "1"},
        [manifest.read_pack(pack)],
        socket="/s.sock",
        scope="local",
        mode="per_user",
        daemon_user=None,
        principal=None,
    )
    head, _, rest = env["PYTHONPATH"].partition(":")
    assert head == str(follow.bootstrap_path())
    assert rest == "/existing"
    # A safe path keeps the script's directory off the head of the path; it does
    # not stop a `sitecustomize` on `PYTHONPATH` from loading, so it is the
    # person's setting to keep, not this flag's to remove.
    assert env["PYTHONSAFEPATH"] == "1"
    assert follow.CONFIG_VARIABLE in env


def test_a_safe_path_still_follows_a_child(tmp_path: Path) -> None:
    """`PYTHONSAFEPATH` set for the whole run: the child still installs the boundary.

    The flag used to claim it cleared the variable because a safe path would
    keep the child from importing the bootstrap; neither half was true. The
    variable was never removed from the program's environment, and a safe path
    does not stop a `sitecustomize` on `PYTHONPATH` from loading — measured
    here as the child's own ask arriving at the daemon.
    """
    tree = _tree(tmp_path)
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--follow-children", "--", "app.py", cwd=tree,
            env={**os.environ, "PYTHONSAFEPATH": "1"},
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert "parent done" in finished.stdout
    assert _asks_for(asks, "process.spawn") == 2


def test_a_child_given_an_import_path_of_its_own_is_not_followed(tmp_path: Path) -> None:
    """The documented limit: a child whose environment REPLACES `PYTHONPATH` —
    `env={**os.environ, "PYTHONPATH": …}` — never sees the bootstrap on it, so it
    runs as it would without the flag. The configuration variable is still there;
    what is gone is the one entry that installs anything. Pinned, so the texts
    that say what the flag covers stay narrower than « every Python child »."""
    tree = tmp_path / "tree"
    tree.mkdir()
    marker = tree / "own-path-child-ran"
    child = f"import subprocess; subprocess.run(['touch', {str(marker)!r}], check=True)"
    (tree / "app.py").write_text(
        "import os, subprocess, sys\n"
        f"subprocess.run([sys.executable, '-c', {child!r}], check=True,\n"
        f"               env={{**os.environ, 'PYTHONPATH': {str(tree)!r}}})\n",
        encoding="utf-8",
    )
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--follow-children", "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert _asks_for(asks, "process.spawn") == 1
    assert marker.exists()


# -- review findings: relative packs, isolated children, prior sitecustomize ------


def test_a_relative_pack_is_resolved_for_a_child_in_another_cwd(tmp_path: Path) -> None:
    """A `--pack ./own-pack` designated in the parent's cwd reaches a child spawned
    in a different cwd: the directory is made absolute before it is handed on, so
    the child does not read `<its-cwd>/own-pack` and die."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "worker").mkdir()
    plant_spawn_pack(tree, name="own-pack")
    child = "import subprocess; subprocess.run(['true'], check=True)"
    (tree / "app.py").write_text(
        "import subprocess, sys\n"
        f"subprocess.run([sys.executable, '-c', {child!r}], check=True, cwd='worker')\n",
        encoding="utf-8",
    )
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run", "--pack", "./own-pack", "--socket", str(socket_path), "--scope", "local",
            "--follow-children", "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    # Parent spawns the child, and the child (in ./worker) governs its own spawn:
    # two asks, which only happens if the child found the pack by its resolved path.
    assert _asks_for(asks, "process.spawn") == 2


def test_a_child_started_isolated_is_not_followed(tmp_path: Path) -> None:
    """The documented limit: a child started with `-S` (or `-I`/`-E`) does not import
    the bootstrap and so is not followed — it runs as it would without the flag,
    never ungoverned-by-a-broken-install. Pinned so it stays a known limit."""
    tree = tmp_path / "tree"
    tree.mkdir()
    marker = tree / "isolated-child-ran"
    child = f"import subprocess; subprocess.run(['touch', {str(marker)!r}], check=True)"
    (tree / "app.py").write_text(
        "import subprocess, sys\n"
        f"subprocess.run([sys.executable, '-S', '-c', {child!r}], check=True)\n",
        encoding="utf-8",
    )
    pack = plant_spawn_pack(tmp_path)
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run", "--pack", str(pack), "--socket", str(socket_path), "--scope", "local",
            "--follow-children", "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    # Only the parent's spawn of the isolated child was asked about; the child's
    # own spawn ran without the boundary, because -S skipped the bootstrap.
    assert _asks_for(asks, "process.spawn") == 1
    assert marker.exists()  # the isolated child ran, as it would without the flag


def _run_child_with_prior(tmp_path: Path, prior_dir: Path) -> tuple[int, str, str]:
    """Run a child with the bootstrap AND a prior sitecustomize on the path, and NO
    follow configuration — so the bootstrap only chains, and the chaining is what is
    under test (no daemon needed)."""
    import subprocess
    import sys

    child = tmp_path / "child.py"
    child.write_text("print('child ran')\n", encoding="utf-8")
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.pathsep.join(
            [
                str(follow.bootstrap_path()),
                str(prior_dir),
                str(Path(__file__).resolve().parents[1] / "src"),
            ]
        ),
    }
    finished = subprocess.run(
        [sys.executable, str(child)], env=environment, capture_output=True, text=True, timeout=60
    )
    return finished.returncode, finished.stdout, finished.stderr


def test_a_prior_sitecustomize_file_with_a_dataclass_still_runs(tmp_path: Path) -> None:
    """Chaining registers the prior module through import resolution, so code that
    looks itself up in sys.modules — a dataclass with postponed annotations — works."""
    prior = tmp_path / "priordir"
    prior.mkdir()
    (prior / "sitecustomize.py").write_text(
        "from __future__ import annotations\n"
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Held:\n"
        "    value: int\n"
        "print('prior ran')\n",
        encoding="utf-8",
    )
    code, out, err = _run_child_with_prior(tmp_path, prior)
    assert code == 0, err
    assert "prior ran" in out and "child ran" in out, (out, err)


def test_a_prior_sitecustomize_package_still_runs(tmp_path: Path) -> None:
    """A `sitecustomize` PACKAGE (not a .py file) is found too, because chaining goes
    through Python's own import resolution rather than a literal file scan."""
    prior = tmp_path / "priordir"
    (prior / "sitecustomize").mkdir(parents=True)
    (prior / "sitecustomize" / "__init__.py").write_text("print('prior ran')\n", encoding="utf-8")
    code, out, err = _run_child_with_prior(tmp_path, prior)
    assert code == 0, err
    assert "prior ran" in out and "child ran" in out, (out, err)
