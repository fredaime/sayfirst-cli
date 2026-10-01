# SPDX-License-Identifier: Apache-2.0
"""The one reader of « the version this tree would release ».

This repository builds two distributions — the client, and the umbrella that
installs the product whole — and releases them under one version. The reading is
written as a module rather than inline in two callers for the same reason the
control plane's is — the changelog guard and the release workflow must agree
about the version, and a version spelled twice is a version that will eventually
be spelled two ways.

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

#: Where each project file this repository builds from lives, relative to its
#: root. The client's is the root's own; the umbrella's is one directory down.
#: A project file that is absent is skipped, so a tree that builds only the
#: client is still read; one that is present and declares no version is
#: refused.
PROJECT_DIRECTORIES: tuple[str, ...] = (".", "umbrella")


def distribution_versions(repository: Path) -> dict[str, str]:
    """Each distribution this repository builds, and the version it carries.

    Raises `ValueError` naming the project file when one declares no version. A
    project file with no `version` is a mistake somebody made, not a release
    candidate, and the reading has to say which file it read: the alternative is
    a `KeyError` in the middle of a release step, which reports a crash rather
    than a refusal and names nothing a reader can go and open.
    """
    versions: dict[str, str] = {}
    for directory in PROJECT_DIRECTORIES:
        project_file = (repository / directory / "pyproject.toml").resolve()
        if directory != "." and not project_file.is_file():
            continue
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
        if "version" not in project:
            raise ValueError(
                f"{project_file} declares no version, so this tree has none to release"
            )
        versions[project["name"]] = project["version"]
    return versions


def release_version(repository: Path) -> str:
    """The version this tree would release.

    Raises `ValueError` when a project file declares none — the reading above
    refuses it — and when the distributions carry more than one version, so
    that a caller gets a refusal rather than a `KeyError` from the middle of a
    workflow, and a tag never publishes two distributions under two numbers.
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
            f"release_version: the tag names {arguments.expect} and the distributions "
            f"carry {version}; nothing is published",
            file=sys.stderr,
        )
        return 1
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
