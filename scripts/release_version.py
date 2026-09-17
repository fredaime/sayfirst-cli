# SPDX-License-Identifier: Apache-2.0
"""The one reader of « the version this tree would release ».

This repository builds one distribution, so the reading is short; it is written
as a module rather than inline in two callers for the same reason the control
plane's is — the changelog guard and the release workflow must agree about the
version, and a version spelled twice is a version that will eventually be
spelled two ways.

The release workflow runs this through uv's own interpreter, never the runner's
system `python`, and passes `--no-project`: this project's own `uv run` cannot
resolve the contract packages from an index, so the invocation names the
interpreter without asking uv to solve this project first.

    uv run --no-project --python 3.12 python scripts/release_version.py
    uv run --no-project --python 3.12 python scripts/release_version.py --expect 0.2.0

The script needs no dependency beyond the standard library's TOML reader, so it
runs the same way under that invocation as it does under a bare interpreter.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


def distribution_versions(repository: Path) -> dict[str, str]:
    """The distribution this repository builds, and the version it carries.

    Raises `ValueError` naming the project file when it declares no version. A
    project file with no `version` is a mistake somebody made, not a release
    candidate, and the reading has to say which file it read: the alternative is
    a `KeyError` in the middle of a release step, which reports a crash rather
    than a refusal and names nothing a reader can go and open.
    """
    project_file = repository / "pyproject.toml"
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
    if "version" not in project:
        raise ValueError(f"{project_file} declares no version, so this tree has none to release")
    return {project["name"]: project["version"]}


def release_version(repository: Path) -> str:
    """The version this tree would release.

    Raises `ValueError` when the project file declares none — the reading above
    refuses it — so that a caller gets a refusal rather than a `KeyError` from
    the middle of a workflow.

    The branch below, which refuses several distributions carrying several
    versions, is reachable only when the reading finds more than one
    distribution. This repository builds one, so it cannot fire here. It is kept
    because the shape is shared with the control plane's reader, where the
    reading walks a directory of distributions and can find two versions among
    them; one shape for one rule is how the two readers go on agreeing, and a
    branch held for parity is worth more than a reading that would have to grow
    the day this repository builds a second distribution.
    """
    versions = distribution_versions(repository)
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        disagreeing = ", ".join(f"{name} {version}" for name, version in sorted(versions.items()))
        raise ValueError(f"the distributions carry more than one version: {disagreeing}")
    return distinct[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect", default=None, help="fail unless this is the version")
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    arguments = parser.parse_args(argv)
    try:
        version = release_version(arguments.repository)
    except ValueError as problem:
        print(f"release_version: {problem}", file=sys.stderr)
        return 1
    if arguments.expect is not None and arguments.expect != version:
        print(
            f"release_version: the tag names {arguments.expect} and this distribution "
            f"carries {version}; nothing is published",
            file=sys.stderr,
        )
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
