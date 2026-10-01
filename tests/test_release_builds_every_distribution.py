# SPDX-License-Identifier: Apache-2.0
"""A tag builds every distribution this repository releases.

The publish job uploads whatever the build job left in `dist/`. The version the
tag is checked against is read from every project file the release reader
knows (`scripts/release_version.py`). So a project directory the reader reads
and the workflow does not build is a distribution whose version was checked,
whose changelog entry was required, and which was then never published — the
release would be green and half of it would be missing from the index.

The rule joins the two lists: every directory the reader reads has its build
line in the workflow.

What it does NOT assert: that the line sits in the build job, runs on a tag, or
writes where the upload reads. It reads the workflow as lines, not as a
document, so a build line moved to another job, put behind a condition or
given another working directory still satisfies it. The release rehearsal and
the review of a workflow change hold those; this guard holds that a project
the version reader reads is never left without its build line.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from release_version import PROJECT_DIRECTORIES

REPOSITORY = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY / ".github" / "workflows" / "release.yml"


def build_line(directory: str) -> str:
    """The command that builds the project in this directory into `dist/`."""
    return "uv build --out-dir dist" if directory == "." else f"uv build {directory} --out-dir dist"


def builds_missing(workflow: str, directories: Iterable[str]) -> list[str]:
    """Every build line the workflow owes and does not carry, as a whole line of a script."""
    lines = {line.strip().removeprefix("run: ") for line in workflow.splitlines()}
    return [
        build_line(directory) for directory in directories if build_line(directory) not in lines
    ]


def test_the_release_builds_every_project_the_version_reader_reads() -> None:
    # Anti-vacuity floor: a reader that read one project would make this the
    # rule that already held before the second distribution existed.
    assert PROJECT_DIRECTORIES == (".", "umbrella")
    for directory in PROJECT_DIRECTORIES:
        assert (REPOSITORY / directory / "pyproject.toml").is_file(), directory
    assert builds_missing(WORKFLOW.read_text(encoding="utf-8"), PROJECT_DIRECTORIES) == []


def test_a_workflow_that_builds_only_the_client_is_caught() -> None:
    """WATCHED FIRING, on the workflow as it stood before the umbrella."""
    before = WORKFLOW.read_text(encoding="utf-8").replace("uv build umbrella --out-dir dist\n", "")
    assert builds_missing(before, PROJECT_DIRECTORIES) == ["uv build umbrella --out-dir dist"]


def test_a_build_line_that_only_resembles_the_owed_one_is_not_accepted() -> None:
    """WATCHED FIRING. A build into another directory is not a build the publish job uploads."""
    elsewhere = (
        "        run: uv build umbrella --out-dir build\n        run: uv build --out-dir dist\n"
    )
    assert builds_missing(elsewhere, PROJECT_DIRECTORIES) == ["uv build umbrella --out-dir dist"]
