# SPDX-License-Identifier: Apache-2.0
"""One repository releases one version, read from both of its project files.

This repository builds two distributions: the client, from the project file at
its root, and the umbrella, from `umbrella/`. A tag names one version, and the
release workflow asks `scripts/release_version.py` whether the tree carries it.
A reader that read only the root would let a tag publish the umbrella under a
number the tag never named.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from release_version import PROJECT_DIRECTORIES, distribution_versions, main, release_version

REPOSITORY = Path(__file__).resolve().parents[1]


def _tree(root: Path, client: str, umbrella: str | None) -> Path:
    """A tree with a client at one version and, unless None, an umbrella at another."""
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "sayfirst-cli"\nversion = "{client}"\n', encoding="utf-8"
    )
    if umbrella is not None:
        (root / "umbrella").mkdir()
        (root / "umbrella" / "pyproject.toml").write_text(
            f'[project]\nname = "sayfirst"\nversion = "{umbrella}"\n', encoding="utf-8"
        )
    return root


def test_the_release_reads_both_distributions_and_finds_one_version() -> None:
    """ANTI-VACUITY as well: a reader that lost the second file would still agree with itself."""
    assert PROJECT_DIRECTORIES == (".", "umbrella")
    versions = distribution_versions(REPOSITORY)
    assert sorted(versions) == ["sayfirst", "sayfirst-cli"]
    assert set(versions.values()) == {release_version(REPOSITORY)}


def test_two_versions_in_one_tree_stop_the_release(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """WATCHED FIRING on the reader the release workflow runs."""
    tree = _tree(tmp_path, "1.0.1", "1.0.0")
    with pytest.raises(ValueError) as refused:
        release_version(tree)
    assert "sayfirst 1.0.0, sayfirst-cli 1.0.1" in str(refused.value)

    assert main(["--repository", str(tree), "--expect", "1.0.1"]) == 1
    printed = capsys.readouterr()
    assert printed.out == "", "a refused reading prints no version"
    assert len(printed.err.splitlines()) == 1, printed.err
    assert "more than one version" in printed.err


def test_a_tag_is_checked_against_both_distributions_at_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tree = _tree(tmp_path, "1.0.1", "1.0.1")
    assert main(["--repository", str(tree), "--expect", "1.0.1"]) == 0
    assert capsys.readouterr().out == "1.0.1\n"
    assert main(["--repository", str(tree), "--expect", "1.0.2"]) == 1
    assert "nothing is published" in capsys.readouterr().err


def test_an_umbrella_with_no_version_is_refused_and_its_file_is_named(tmp_path: Path) -> None:
    """WATCHED FIRING. The refusal names the file a reader has to open, not the root's."""
    tree = _tree(tmp_path, "1.0.1", None)
    (tree / "umbrella").mkdir()
    (tree / "umbrella" / "pyproject.toml").write_text(
        '[project]\nname = "sayfirst"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError) as refused:
        release_version(tree)
    assert str(Path("umbrella") / "pyproject.toml") in str(refused.value)
    assert "declares no version" in str(refused.value)


def test_a_tree_that_builds_only_the_client_is_still_read(tmp_path: Path) -> None:
    """An unpacked source distribution of another shape, or a tree before the umbrella."""
    tree = _tree(tmp_path, "1.0.1", None)
    assert distribution_versions(tree) == {"sayfirst-cli": "1.0.1"}
    assert release_version(tree) == "1.0.1"
