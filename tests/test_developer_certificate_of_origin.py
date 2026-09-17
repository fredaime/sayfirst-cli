# SPDX-License-Identifier: Apache-2.0
"""Articles 15 and 16: the sign-off is read, not remembered.

Article 15 asks that every contributor sign off each commit and article 16 calls
the check required. Until now nothing in this repository read a trailer: the rule
was a sentence of `README.md` held by whoever happened to look, which is the
shape article 2 calls a claim with no evidence behind it.

The mechanism is `scripts/check_developer_certificate_of_origin.py`, and it is
proved here against real commits in a throwaway repository — the defect planted
rather than assumed, because a check nobody has watched refuse is not a check.
Three exit codes, three cases: a range that certifies throughout, a range with
one commit that does not, and a range that cannot be read at all. The third is
the one a shallow checkout produces, and reporting it as a pass is the failure
this exit code exists to prevent.

Whether the public repository's branch protection marks the job *required* is a
setting of that repository, which this test cannot read and does not claim; it
is a line of `docs/publication-checklist.md` instead.

One rule per file, so a new rule arrives as a new file and a new file never
conflicts (article 16).

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "check_developer_certificate_of_origin.py"

sys.path.insert(0, str(REPOSITORY / "scripts"))

from check_developer_certificate_of_origin import (  # noqa: E402
    RangeUnreadable,
    uncertified,
)


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repository, capture_output=True, text=True, check=True
    )
    return result.stdout


def _repository_with(commits: list[tuple[str, bool]], root: Path) -> Path:
    """A throwaway history, one commit per entry, signed off where asked.

    Built here rather than read from this checkout: a test that read the real
    history would pass or fail on what somebody committed last week, and could
    not plant the commit it exists to refuse.
    """
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "A Contributor")
    _git(root, "config", "user.email", "contributor@example.org")
    (root / "file").write_text("base\n", encoding="utf-8")
    _git(root, "add", "file")
    _git(root, "commit", "-q", "-s", "-m", "the commit the range starts from")
    for subject, signed in commits:
        (root / "file").write_text(subject, encoding="utf-8")
        _git(root, "add", "file")
        _git(root, "commit", "-q", *(["-s"] if signed else []), "-m", subject)
    return root


def test_a_range_that_certifies_throughout_passes(tmp_path: Path) -> None:
    """ANTI-VACUITY. The check that refuses below must accept a correct range, or
    it is a check that refuses everything and proves nothing."""
    root = _repository_with(
        [("a signed change", True), ("another signed change", True)], tmp_path / "clean"
    )
    assert uncertified("main~2", "main", repository=root) == []


def test_a_commit_without_a_sign_off_fails_the_check(tmp_path: Path) -> None:
    """WATCHED FIRING. Article 15: the certificate is what the trailer certifies;
    no trailer, no certificate. The refused commit is named, so a contributor
    knows which one to repair."""
    root = _repository_with(
        [("a signed change", True), ("a change nobody certified", False)], tmp_path / "planted"
    )
    missing = uncertified("main~2", "main", repository=root)
    assert len(missing) == 1, missing
    assert "a change nobody certified" in missing[0]


def test_a_range_that_cannot_be_read_is_never_reported_as_passing(tmp_path: Path) -> None:
    """WATCHED FIRING on the third outcome. Article 2: a shallow checkout has no
    range, and no range is not a pass — the check raises rather than returning an
    empty list, which is what an unreadable range and a clean one would otherwise
    both look like."""
    root = _repository_with([("a signed change", True)], tmp_path / "unreadable")
    with pytest.raises(RangeUnreadable):
        uncertified("no-such-ref", "main", repository=root)


def test_a_merge_commit_is_passed_over(tmp_path: Path) -> None:
    """WATCHED NOT FIRING. A merge introduces no work of its own and its parents
    are checked where they were made, so refusing it would turn the certificate
    into a rule about merge strategy and be worked around within a week."""
    root = _repository_with([("a signed change", True)], tmp_path / "merge")
    _git(root, "checkout", "-q", "-b", "side", "main~1")
    (root / "other").write_text("side\n", encoding="utf-8")
    _git(root, "add", "other")
    _git(root, "commit", "-q", "-s", "-m", "a signed change on a side branch")
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "--no-edit", "side")
    # `~` walks FIRST PARENTS, so the chain from the merge is merge -> the signed
    # change -> the base, and `main~2` is the base. The side branch's commit is in
    # the range without being on that walk, which is exactly what the range has to
    # cover; `main~3` names nothing here and would be read as an unreadable range.
    assert uncertified("main~2", "main", repository=root) == []


def test_the_script_answers_with_each_of_its_three_exit_codes(tmp_path: Path) -> None:
    """Article 16: the check is a step of a workflow, so the exit code is the
    verdict and nothing else is read. All three are run, because a code nobody
    has seen produced is a code nobody can rely on."""
    signed = _repository_with([("a signed change", True)], tmp_path / "zero")
    unsigned = _repository_with([("a change nobody certified", False)], tmp_path / "one")

    def run(root: Path, base: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--base", base, "--head", "main"],
            cwd=root,
            capture_output=True,
            text=True,
        )

    green = run(signed, "main~1")
    assert green.returncode == 0, green.stdout + green.stderr

    refused = run(unsigned, "main~1")
    assert refused.returncode == 1, refused.stdout + refused.stderr
    assert "a change nobody certified" in refused.stderr

    unreadable = run(signed, "no-such-ref")
    assert unreadable.returncode == 2, unreadable.stdout + unreadable.stderr
    assert "could not be read" in unreadable.stderr
