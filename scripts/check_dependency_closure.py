# SPDX-License-Identifier: Apache-2.0
"""Article 13 and 14, measured after an install rather than promised in a file.

    "The command-line client depends on the contract distribution and never on
    the server distribution, so installing it never installs a web framework or
    a database layer."  — constitution, article 14

A declared dependency list is a claim; a dependency *closure* is a fact. This
script builds this distribution, installs it into an empty environment, and
reads back every distribution that arrived with it. The rule it holds is stated
in the positive — what the closure must be — because a guard written as a list
of forbidden words is a guard that only catches the words someone thought of,
and, where the words are private, is itself the leak.

The forbidden categories the article names are checked too, as a second and
weaker statement, so that a failure can quote the article back in its own words.
That check has a list in it; every name on it is a well-known public package,
so the list discloses nothing.

Run it, and it proves itself: after the real closure passes, it plants a web
framework into the same environment and requires the check to fail. A gate that
has never been seen to fail is not known to be a gate.

**Article 9's packs are measured here for the same reason.** A pack is data
beside the code that loads it — a manifest and a note, neither of them Python —
so a wheel that ships only `.py` files ships a client that governs nothing,
and every test that reads the packs through an *editable* install still passes,
because an editable install resolves to the source tree. This is the one step
of the gate that reads them out of an environment built from the actual wheel,
which is what makes it the place the packaging rule can fail.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

# The one name this step needs from the client it measures: what a pack's
# manifest is called. Read from the client rather than spelled here a second
# time — two copies of one rule is how a gate and its project stop agreeing —
# and it is the *file name* only, never the answer to what is installed, which
# is asked of the built wheel in an environment of its own below.
from sayfirst_cli.instrument.manifest import MANIFEST_FILE

REPOSITORY = Path(__file__).resolve().parents[1]

#: Where this repository keeps article 9's packs. The step already runs inside
#: the repository, which is the only place the answer to « how many packs should
#: have arrived » is known: a count read out of the wheel would be the wheel
#: agreeing with itself.
PACKS_DIRECTORY = REPOSITORY / "src" / "sayfirst_cli" / "packs"

#: Everything this client's installed closure may contain, and nothing else.
#: `sayfirst-cli` is the distribution itself; `sayfirst-contract` and
#: `sayfirst-boundary` are the two dependencies article 13 and article 10
#: allow — the boundary is the runtime a governed program holds a grant in,
#: and it depends on the contract alone. The standard library is not a
#: distribution and does not appear here.
PERMITTED_CLOSURE: frozenset[str] = frozenset(
    {"sayfirst-cli", "sayfirst-contract", "sayfirst-boundary"}
)

#: Public names of the two categories article 14 forbids by name. This list is
#: not the rule — `PERMITTED_CLOSURE` is — and it exists so that a failure can
#: say *which* of the article's two words was broken.
WEB_FRAMEWORKS: frozenset[str] = frozenset(
    {
        "aiohttp",
        "bottle",
        "cherrypy",
        "django",
        "falcon",
        "fastapi",
        "flask",
        "hypercorn",
        "litestar",
        "pyramid",
        "quart",
        "sanic",
        "starlette",
        "tornado",
        "uvicorn",
        "waitress",
        "werkzeug",
    }
)
DATABASE_LAYERS: frozenset[str] = frozenset(
    {
        "alembic",
        "asyncpg",
        "mysqlclient",
        "peewee",
        "pg8000",
        "psycopg",
        "psycopg2",
        "psycopg2-binary",
        "pymongo",
        "pymysql",
        "redis",
        "sqlalchemy",
        "sqlmodel",
        "tortoise-orm",
    }
)


def normalise(name: str) -> str:
    """A distribution name as an index compares it (PEP 503)."""
    return "".join("-" if character in "-_." else character for character in name.lower())


def unpermitted(closure: Iterable[str]) -> list[str]:
    """Distributions in the closure that the positive rule does not permit."""
    return sorted({normalise(name) for name in closure} - PERMITTED_CLOSURE)


def forbidden_by_category(closure: Iterable[str]) -> dict[str, list[str]]:
    """The article's own two words, and what in the closure broke each of them."""
    installed = {normalise(name) for name in closure}
    found = {
        "a web framework": sorted(installed & WEB_FRAMEWORKS),
        "a database layer": sorted(installed & DATABASE_LAYERS),
    }
    return {category: names for category, names in found.items() if names}


def failures(closure: Iterable[str]) -> list[str]:
    """Every way this closure breaks articles 13 and 14, said one line each."""
    installed = list(closure)
    reported = []
    # Anti-vacuity floor: a closure that does not contain the distribution
    # itself is an install that did not happen, not a closure that is clean.
    if "sayfirst-cli" not in {normalise(name) for name in installed}:
        reported.append("the closure does not contain sayfirst-cli: nothing was installed")
    if extra := unpermitted(installed):
        reported.append(f"the closure contains distributions article 13 does not permit: {extra}")
    for category, names in forbidden_by_category(installed).items():
        reported.append(f"installing the client installed {category}: {names}")
    return reported


#: Asked of the installed environment, never answered here: the question is
#: what the built wheel actually put there. It calls the client's own reader —
#: `shipped_packs()`, the one `sayfirst packs list` uses — so this measures the
#: packaging rather than forming a second opinion about it, and reports the
#: packs directory's entries as well, because « no pack arrived » is a fact a
#: reader needs the directory listing to act on.
PACKS_PROGRAM = (
    "import importlib.resources as resources, json;"
    "from sayfirst_cli.packs_cmd import shipped_packs;"
    "from sayfirst_cli.instrument.manifest import REQUIRED_FILES;"
    "root = resources.files('sayfirst_cli.packs');"
    "inside = sorted(root.iterdir(), key=lambda item: item.name) if root.is_dir() else [];"
    "missing = lambda item: [name for name in REQUIRED_FILES if not (item / name).is_file()];"
    "print(json.dumps({"
    "'root': str(root),"
    "'entries': [item.name for item in inside],"
    "'read': sorted(pack.name for pack in shipped_packs()),"
    "'packs': {item.name: missing(item) for item in inside"
    " if item.is_dir() and len(missing(item)) < len(REQUIRED_FILES)}"
    "}))"
)


def read_packs(python: Path) -> dict[str, object]:
    """What the installed distribution carries under `sayfirst_cli.packs`.

    `read` is what the client's own reader admits; `packs` is every directory
    there that carries at least one of a pack's three files, with whatever it
    is missing. The second exists because a pack stripped of its manifest is
    invisible to the reader — it is simply not a pack any more — and « nothing
    is there » is the least useful thing a packaging failure can say.

    A client whose packs package cannot even be imported is a packaging failure
    like any other, so it comes back as one — an unreadable answer rather than
    a traceback out of this gate.
    """
    finished = subprocess.run((str(python), "-c", PACKS_PROGRAM), capture_output=True, text=True)
    if finished.returncode != 0:
        return {"root": "(could not be read)", "entries": [], "packs": {}, "why": finished.stderr}
    return json.loads(finished.stdout)


def carried_packs(found: dict[str, object]) -> list[str]:
    """The packs an install really carries: admitted by the reader, and complete."""
    packs: dict[str, list[str]] = dict(found.get("packs") or {})  # type: ignore[arg-type]
    read = set(found.get("read") or [])  # type: ignore[arg-type]
    return sorted(name for name, missing in packs.items() if not missing and name in read)


def shipped_pack_names() -> list[str]:
    """Every pack name this repository ships, read off the source tree.

    A directory counts by carrying a manifest, which is how the client's own
    reader counts one: a `__pycache__` beside the packs is not a pack, and is
    not a reason this walk fails either.
    """
    if not PACKS_DIRECTORY.is_dir():
        return []
    return sorted(
        item.name
        for item in PACKS_DIRECTORY.iterdir()
        if item.is_dir() and (item / MANIFEST_FILE).is_file()
    )


def pack_failures(found: dict[str, object], expected: Iterable[str] | None = None) -> list[str]:
    """Every way an install failed to carry article 9's packs, said one line each.

    The rule is EVERY pack and not one of them. A floor of one passed a wheel
    that shipped the first of three and dropped the other two — reported as
    « the wheel carries 1 pack(s) » — and nothing else in the gate can see that:
    every other reader of the packs resolves to the source tree under the
    editable install the gate uses, which `tests/test_packs_shipped.py` says of
    itself.

    `expected` is what the repository ships, read off the source tree by
    default, because that is the one place the answer is known independently of
    the thing being measured.
    """
    packs: dict[str, list[str]] = dict(found.get("packs") or {})  # type: ignore[arg-type]
    reported = [
        f"the pack {name!r} arrived without {missing}"
        for name, missing in sorted(packs.items())
        if missing
    ]
    carried = carried_packs(found)
    wanted = sorted(shipped_pack_names() if expected is None else set(expected))
    if not wanted:
        # Anti-vacuity, and held here rather than only in a test: with nothing
        # to look for, the comparison below passes over any wheel at all and
        # this step would report an absence as a healthy state (article 2).
        reported.append(
            "this repository declares no pack for the step to look for: a rule with "
            "an empty right-hand side is not a rule"
        )
    if missing := sorted(set(wanted) - set(carried)):
        reported.append(
            f"the wheel carries {carried} and not {missing}: every pack this repository "
            f"ships has to arrive with the client (article 9), and a wheel carrying some "
            f"of them ships a client that governs less than its own documentation says"
        )
    if not carried:
        why = str(found.get("why") or "").strip()
        reported.append(
            f"no complete pack arrived with the client: {found.get('root')} holds "
            f"{found.get('entries')}. A pack is a manifest, an execution module and a "
            f"note (article 9), and only the second of the three is Python — a wheel "
            f"that ships .py files alone ships a client that governs nothing"
            + (f". The packs package could not be read: {why}" if why else "")
        )
    return reported


def read_closure(python: Path) -> list[str]:
    """Every distribution installed in the environment of one interpreter."""
    program = (
        "import json,importlib.metadata as m;"
        "print(json.dumps(sorted(d.metadata['Name'] for d in m.distributions())))"
    )
    output = subprocess.run(
        (str(python), "-c", program), capture_output=True, text=True, check=True
    ).stdout
    return json.loads(output)


def plant_a_web_framework(site_packages: Path, name: str = "starlette") -> Path:
    """Install the metadata of a web framework, and nothing else, into a closure.

    The defect the guard exists to catch is "a web framework is in the installed
    closure". `importlib.metadata` answers that question from `.dist-info`
    directories, so a `.dist-info` directory is the whole defect — no download,
    no network, and nothing left behind outside the throwaway environment.
    """
    planted = site_packages / f"{name}-0.0.0.dist-info"
    planted.mkdir(parents=True)
    (planted / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0.0\n", encoding="utf-8"
    )
    (planted / "INSTALLER").write_text("planted-by-the-gate\n", encoding="utf-8")
    return planted


def site_packages_of(python: Path) -> Path:
    output = subprocess.run(
        (str(python), "-c", "import sysconfig;print(sysconfig.get_paths()['purelib'])"),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return Path(output.strip())


def _build(source: Path, destination: Path, package: str | None = None) -> None:
    command = ["uv", "build", "--wheel", "-o", str(destination)]
    if package is not None:
        command += ["--package", package]
    subprocess.run(command, cwd=source, check=True, stdout=subprocess.DEVNULL)


def _contract_source(given: str | None) -> Path:
    """Where a checkout of the control plane repository is on this machine.

    `sayfirst-contract` is on no index: article 0 forbids publishing anything
    until the marks are filed. So the gate is told where the contract is, and it
    *fails* when it is not told — never skips. A skipped guard is a guard that
    cannot fail.
    """
    default = REPOSITORY.parent / "sf-control-plane-lt"
    source = Path(given) if given else default
    if not (source / "packages" / "contract" / "pyproject.toml").is_file():
        raise SystemExit(
            f"no checkout of the control plane repository at {source}. "
            "Pass --contract-source, or set it to a directory that has "
            "packages/contract/pyproject.toml. The contract distribution is not "
            "published (article 0), so this gate cannot fetch it from an index."
        )
    return source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_dependency_closure")
    parser.add_argument("--contract-source", default=None)
    parser.add_argument("--python", default="3.13")
    arguments = parser.parse_args(argv)
    contract = _contract_source(arguments.contract_source)

    with tempfile.TemporaryDirectory(prefix="sayfirst-closure-") as scratch:
        root = Path(scratch)
        wheelhouse = root / "wheelhouse"
        wheelhouse.mkdir()
        _build(contract, wheelhouse, package="sayfirst-contract")
        # The boundary is now a dependency of the client (article 10), so its
        # wheel has to be in the same offline find-links directory or the
        # install below cannot resolve it.
        _build(contract, wheelhouse, package="sayfirst-boundary")
        _build(REPOSITORY, wheelhouse)

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
                "sayfirst-cli",
            ),
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            # A closure that cannot be formed offline is a failure of this gate
            # and not a crash of it: the one thing article 13 asks is that the
            # client resolve against the contract and the standard library, and
            # a dependency that has to be fetched from an index is the same
            # defect seen one step earlier.
            print(
                "FAIL the closure could not be installed from the contract alone. "
                "A dependency that resolves only against an index is a dependency "
                "articles 13 and 14 do not permit.",
                file=sys.stderr,
            )
            print(install.stderr.strip(), file=sys.stderr)
            return 1

        closure = read_closure(python)
        print(f"installed closure: {closure}")
        if reported := failures(closure):
            for line in reported:
                print(f"FAIL {line}", file=sys.stderr)
            return 1
        print(
            "PASS the installed closure is the client, the contract and the boundary "
            "runtime, and nothing else"
        )

        # Article 9, in the same environment and for the same reason: measured
        # after an install rather than promised in `pyproject.toml`.
        found = read_packs(python)
        if reported := pack_failures(found):
            for line in reported:
                print(f"FAIL {line}", file=sys.stderr)
            return 1
        carried = carried_packs(found)
        print(
            f"PASS the wheel carries every pack this repository ships ({len(carried)}): {carried}"
        )

        # The self-proof. It runs on the real environment that has just passed,
        # so what it proves is that this run's check would have caught it.
        planted = plant_a_web_framework(site_packages_of(python))
        after = read_closure(python)
        caught = failures(after)
        shutil.rmtree(planted)
        if not caught:
            print(
                "FAIL the planted web framework was not caught: this guard cannot fail",
                file=sys.stderr,
            )
            return 1
        print("PASS the guard rejects a planted web framework, on both counts:")
        for line in caught:
            print(f"     would have failed: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
