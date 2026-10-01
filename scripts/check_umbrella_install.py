# SPDX-License-Identifier: Apache-2.0
"""What installing `sayfirst` brings, measured after an install rather than promised in a file.

This repository builds two distributions. `sayfirst-cli` is the client, and
`scripts/check_dependency_closure.py` holds what installing it brings: three
distributions, never the server (article 14). `sayfirst` is the product
installed whole: it installs no module, depends on the client, on the daemon and
on the daemon's operator surface, and names their three commands so that an
installer which exposes only the commands of the package it was handed exposes
all three.

Three rules, each measured on a real install into an empty environment:

* **The closure is six distributions of this project and nothing else.** Stated
  in the positive, as the client's own closure rule is: a list of forbidden
  names catches only the names somebody thought of.
* **Every command the umbrella names is declared, word for word, by the
  distribution that owns it.** The umbrella's entry points are mirrors. A
  mirror that drifts from its owner points a command at code the owner no
  longer ships, and nothing in this repository's own tree can see the owners
  that live in the control plane's — so the comparison is made where all four
  distributions are installed side by side.
* **Each of the three commands starts.** `--help` answers 0 from the
  environment the install made.

A fourth rule needs no install and is held from the two project files: the
umbrella pins its three dependencies to its own version, which is the client's.

Run it, and it proves itself: after the real install passes, it plants a
distribution into the same environment and requires the closure rule to fail.
A gate that has never been seen to fail is not known to be a gate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

#: The directory of the second distribution this repository builds.
UMBRELLA = REPOSITORY / "umbrella"

#: The distribution this script measures.
UMBRELLA_NAME = "sayfirst"

#: Which distribution owns each command the umbrella names. The left column is
#: also the whole set of commands the umbrella may declare.
OWNERS: Mapping[str, str] = {
    "sayfirst": "sayfirst-cli",
    "sayfirst-daemon": "sayfirst-control-plane",
    "sayfirstd": "sayfirstd",
}

#: Everything the installed closure of the umbrella is, and nothing else: the
#: umbrella, the three owners, and the two distributions the owners depend on.
#: The standard library is not a distribution and does not appear here.
EXPECTED_CLOSURE: frozenset[str] = frozenset(
    {UMBRELLA_NAME, *OWNERS.values(), "sayfirst-contract", "sayfirst-boundary"}
)


def normalise(name: str) -> str:
    """A distribution name as an index compares it (PEP 503)."""
    return "".join("-" if character in "-_." else character for character in name.lower())


def closure_failures(closure: Iterable[str]) -> list[str]:
    """Every way an installed closure is not the six distributions, one line each."""
    installed = {normalise(name) for name in closure}
    reported = []
    # Anti-vacuity floor: a closure without the umbrella is an install that did
    # not happen, not a closure that is clean.
    if UMBRELLA_NAME not in installed:
        reported.append(f"the closure does not contain {UMBRELLA_NAME}: nothing was installed")
    if missing := sorted(EXPECTED_CLOSURE - installed):
        reported.append(f"the install did not bring {missing}: the product is not whole")
    if extra := sorted(installed - EXPECTED_CLOSURE):
        reported.append(f"the install brought distributions the product does not name: {extra}")
    return reported


def mirror_failures(declared: Mapping[str, Mapping[str, str]]) -> list[str]:
    """Every way the umbrella's commands differ from what their owners declare.

    `declared` maps a distribution's name to the console scripts it declares,
    each as `name -> target`, read from an installed environment.
    """
    by_name = {normalise(name): dict(scripts) for name, scripts in declared.items()}
    mirrored = by_name.get(UMBRELLA_NAME, {})
    reported = []
    if unknown := sorted(set(mirrored) - set(OWNERS)):
        reported.append(f"the umbrella declares commands no distribution owns: {unknown}")
    for command, owner in sorted(OWNERS.items()):
        owned = by_name.get(owner, {}).get(command)
        if owned is None:
            reported.append(f"{owner} declares no command {command!r} for the umbrella to mirror")
        elif command not in mirrored:
            reported.append(f"the umbrella does not name {command!r}, which {owner} declares")
        elif mirrored[command] != owned:
            reported.append(
                f"{command!r}: the umbrella points at {mirrored[command]!r} "
                f"and {owner} declares {owned!r}"
            )
    return reported


def pin_failures(umbrella: Mapping[str, object], client: Mapping[str, object]) -> list[str]:
    """Every way the umbrella's project table breaks « three pins, one version ».

    Both arguments are `[project]` tables: the umbrella's, and the client's,
    whose version is the one this repository releases.
    """
    version = client.get("version")
    reported = []
    if umbrella.get("version") != version:
        reported.append(
            f"the umbrella carries {umbrella.get('version')} and the client {version}: "
            f"one repository releases one version"
        )
    wanted = sorted(f"{owner}=={version}" for owner in OWNERS.values())
    declared = umbrella.get("dependencies")
    found = sorted(str(item) for item in declared) if isinstance(declared, list) else []
    if found != wanted:
        reported.append(f"the umbrella depends on {found} and the rule is exactly {wanted}")
    extras = umbrella.get("optional-dependencies")
    if extras:
        named = sorted(extras) if isinstance(extras, dict) else extras
        reported.append(
            f"the umbrella declares extras {named}: "
            f"the product is three pins, and an extra is a fourth dependency by another door"
        )
    return reported


def project_table(directory: Path) -> dict[str, object]:
    """The `[project]` table of the project file in this directory."""
    return tomllib.loads((directory / "pyproject.toml").read_text(encoding="utf-8"))["project"]


#: Asked of the installed environment, never answered here: which console
#: scripts each installed distribution declares.
SCRIPTS_PROGRAM = (
    "import json, importlib.metadata as m;"
    "print(json.dumps({d.metadata['Name']: "
    "{e.name: e.value for e in d.entry_points if e.group == 'console_scripts'} "
    "for d in m.distributions()}))"
)


def read_scripts(python: Path) -> dict[str, dict[str, str]]:
    """The console scripts every distribution of one environment declares."""
    output = subprocess.run(
        (str(python), "-c", SCRIPTS_PROGRAM), capture_output=True, text=True, check=True
    ).stdout
    return json.loads(output)


def command_failures(binaries: Path) -> list[str]:
    """Every command of the umbrella that does not start from this environment."""
    reported = []
    for command in sorted(OWNERS):
        executable = binaries / command
        if not executable.is_file():
            reported.append(f"the install left no {command} beside its interpreter")
            continue
        finished = subprocess.run((str(executable), "--help"), capture_output=True, text=True)
        if finished.returncode != 0:
            said = finished.stderr.strip().splitlines()
            reported.append(
                f"{command} --help answered {finished.returncode}: "
                f"{said[-1] if said else 'nothing on its error stream'}"
            )
    return reported


def main(argv: list[str] | None = None) -> int:
    # Read here and not at the top of this file: the helpers below install and
    # build, and their module imports the client, which a machine with no
    # contract cannot import. The rules above are importable everywhere, so the
    # tests that plant defects against them speak in a reduced run too.
    import check_dependency_closure as closure_check

    parser = argparse.ArgumentParser(prog="check_umbrella_install")
    parser.add_argument("--contract-source", default=None)
    parser.add_argument("--python", default="3.13")
    arguments = parser.parse_args(argv)
    control_plane = closure_check._contract_source(arguments.contract_source)

    if reported := pin_failures(project_table(UMBRELLA), project_table(REPOSITORY)):
        for line in reported:
            print(f"FAIL {line}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="sayfirst-umbrella-") as scratch:
        root = Path(scratch)
        wheelhouse = root / "wheelhouse"
        wheelhouse.mkdir()
        for package in (
            "sayfirst-contract",
            "sayfirst-boundary",
            "sayfirst-control-plane",
            "sayfirstd",
        ):
            closure_check._build(control_plane, wheelhouse, package=package)
        closure_check._build(REPOSITORY, wheelhouse)
        closure_check._build(UMBRELLA, wheelhouse)

        environment = root / "environment"
        subprocess.run(
            ("uv", "venv", "--python", arguments.python, str(environment)),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        python = environment / "bin" / "python"
        install = subprocess.run(
            (
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-index",
                "--find-links",
                str(wheelhouse),
                UMBRELLA_NAME,
            ),
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            print(
                "FAIL the product could not be installed from this project's own "
                "distributions. A dependency that resolves only against an index is "
                "one the umbrella does not name.",
                file=sys.stderr,
            )
            print(install.stderr.strip(), file=sys.stderr)
            return 1

        installed = closure_check.read_closure(python)
        print(f"installed closure: {installed}")
        reported = closure_failures(installed)
        reported += mirror_failures(read_scripts(python))
        reported += command_failures(environment / "bin")
        if reported:
            for line in reported:
                print(f"FAIL {line}", file=sys.stderr)
            return 1
        print("PASS installing sayfirst brings six distributions of this project, and nothing else")
        print("PASS each command the umbrella names is declared, word for word, by its owner")
        print(f"PASS the commands start from that environment: {sorted(OWNERS)}")

        # The self-proof. It runs on the environment that has just passed, so
        # what it proves is that this run's check would have caught it.
        planted = closure_check.plant_a_web_framework(closure_check.site_packages_of(python))
        caught = closure_failures(closure_check.read_closure(python))
        shutil.rmtree(planted)
        if not caught:
            print(
                "FAIL a planted distribution was not caught: this guard cannot fail",
                file=sys.stderr,
            )
            return 1
        print("PASS the guard rejects a planted distribution:")
        for line in caught:
            print(f"     would have failed: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
