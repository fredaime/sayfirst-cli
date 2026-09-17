# SPDX-License-Identifier: Apache-2.0
"""Article 16: every release carries a changelog, so a release without one is red.

The guard reads the FIRST heading that is a version. `## Unreleased` sits above
them and is skipped on purpose: ordinary development appends to it, and a guard
that demanded a release heading at the top would be red on every working branch
and would teach people to ignore it.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
CHANGELOG = REPOSITORY / "CHANGELOG.md"

sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_version import main, release_version  # noqa: E402

#: A release section's heading: two hashes, a semantic version, nothing else
#: required after it.
RELEASE_HEADING = re.compile(r"^## (\d+\.\d+\.\d+)\b", re.MULTILINE)


def top_release(changelog: str) -> str | None:
    """The version of the newest release section, or None when there is none."""
    found = RELEASE_HEADING.search(changelog)
    return found.group(1) if found else None


def test_the_changelog_names_the_version_this_tree_would_release() -> None:
    """Article 16: a release with no entry is red before it is tagged."""
    assert top_release(CHANGELOG.read_text(encoding="utf-8")) == release_version(REPOSITORY)


def test_an_unreleased_section_above_the_release_is_not_mistaken_for_one() -> None:
    """WATCHED NOT FIRING."""
    assert (
        top_release("# Changelog\n\n## Unreleased\n\n- a change\n\n## 0.2.0\n\n- shipped\n")
        == "0.2.0"
    )


def test_a_changelog_with_no_entry_for_the_version_is_caught() -> None:
    """WATCHED FIRING."""
    assert top_release("# Changelog\n\n## Unreleased\n\n- a change\n") is None
    assert top_release("# Changelog\n\n## 0.1.0\n\n- shipped\n") != release_version(REPOSITORY)


def test_a_project_file_with_no_version_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WATCHED FIRING on the reader itself, and on what a caller sees.

    A workflow that got a `KeyError` from the middle of a release step would
    report a crash, not a refusal — so the function raises `ValueError` naming
    the file it read, and `pytest.raises(ValueError)` is red on a `KeyError`
    rather than satisfied by it. The command is read too: a refusal nobody
    catches is a traceback, so `main` answers 1 and says why in one sentence.
    """
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "sayfirst-cli"\n', encoding="utf-8")
    with pytest.raises(ValueError) as refused:
        release_version(tmp_path)
    assert "pyproject.toml" in str(refused.value)
    assert "declares no version" in str(refused.value)

    assert main(["--repository", str(tmp_path)]) == 1
    printed = capsys.readouterr()
    assert printed.out == "", "a refused reading prints no version"
    assert len(printed.err.splitlines()) == 1, printed.err
    assert "declares no version" in printed.err
