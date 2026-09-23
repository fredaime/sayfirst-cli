# SPDX-License-Identifier: Apache-2.0
"""Article 0: the decided name is the only name, and no placeholder survives here.

Article 0 held the project's public name behind a placeholder and made replacing
every occurrence of it one of the three conditions for publishing anything. The
name was decided on 2026-09-04 and this repository's occurrences were replaced.
What that leaves is a hole a later commit falls into: the placeholder was
written three ways — angle-bracketed in prose, hyphenated for a distribution
name, underscored for an import package, because Core Metadata cannot carry an
angle bracket — and any of the three can be typed again from memory or arrive in
a merge. A retired *candidate* name is a fourth hazard, because this repository
carried one for a day.

The fifth thing guarded here is not a placeholder at all. A blanket substring
replacement in this project once turned "mandatory" into a word with the brand
glued inside it, across twelve files, and reached an artefact pinned by its
bytes; it was caught by a person reading the diff, and by no test. So the
decided name is required to stand as a word: an occurrence followed by a letter
is that defect, and it is now a red test rather than a paragraph in a document.

Every pattern is assembled from pieces so that this file is not itself the
occurrence it forbids — the idiom the control plane repository uses for the
same reason.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

#: The name the operator decided on 2026-09-04. One word, so the distribution
#: prefix, the import prefix and the command are the same string.
DECIDED_NAME = "sayfirst"

#: Directories a non-git enumeration must not walk into.
UNTRACKED_DIRECTORIES = frozenset(
    {".git", ".venv", ".wheelhouse", "__pycache__", ".ruff_cache", ".pytest_cache", "dist"}
)

#: The retired placeholder in each of the three ways it was written. `<...>` is
#: optional because the bare renderings are occurrences in their own right, and
#: the separator is either character because both renderings existed.
_PLACEHOLDER_STEM = "oss" + "[-_]" + "brand"
PLACEHOLDER = re.compile("<?" + _PLACEHOLDER_STEM + ">?", re.IGNORECASE)

#: The name a branch of this repository carried for one day before the operator
#: settled N1. Bounded as a word, and as a prefix before a separator, so that
#: the ordinary English words it is the stem of are not occurrences of it.
_RETIRED_CANDIDATE = "man" + "dat"
RETIRED_CANDIDATE = re.compile(
    r"\b" + _RETIRED_CANDIDATE + r"(?![A-Za-z])|\b" + _RETIRED_CANDIDATE + r"[-_]",
    re.IGNORECASE,
)

#: The decided name with a letter welded to it — the shape a blanket substring
#: replacement leaves behind, and the defect this project has already had.
#:
#: One welded form is a name and not that defect: the daemon's operator surface
#: is a published command spelled with a `d` after the decided name, by the
#: ordinary convention for a daemon's own tool, and the quickstart has to be
#: able to tell a reader to type it. It is admitted as exactly that word — the
#: `d` and then no letter — so that the defect it resembles (the same stem
#: running on into a longer word) is still caught, which the planted cases
#: below hold in both directions.
_OPERATOR_SUFFIX = "d"
GLUED_NAME = re.compile(
    "(?<![A-Za-z])" + DECIDED_NAME + "(?!" + _OPERATOR_SUFFIX + "(?![A-Za-z]))" + "(?=[A-Za-z])",
    re.IGNORECASE,
)

PATTERNS = {
    "placeholder": PLACEHOLDER,
    "retired candidate": RETIRED_CANDIDATE,
    "the decided name glued into a word": GLUED_NAME,
}


def _tracked_files(root: Path) -> list[Path]:
    """Every file this repository would publish, as repository-relative paths."""
    if (root / ".git").exists() and shutil.which("git") is not None:
        listed = subprocess.run(
            ("git", "ls-files", "-z"), cwd=root, capture_output=True, text=True, check=True
        ).stdout
        return [Path(name) for name in listed.split("\0") if name]
    return sorted(
        item.relative_to(root)
        for item in root.rglob("*")
        if item.is_file() and not UNTRACKED_DIRECTORIES & set(item.relative_to(root).parts)
    )


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def occurrences(root: Path) -> Iterator[tuple[Path, str, str]]:
    """Yield (file, which pattern, matched text) for everything still to replace.

    Both the path and the bytes are read: a module can return under the retired
    import prefix without a sentence ever naming it.
    """
    for item in _tracked_files(root):
        content = _read(root / item)
        for label, pattern in PATTERNS.items():
            in_path = pattern.search(item.as_posix())
            if in_path is not None:
                yield item, label, in_path.group(0)
            if content is None:
                continue
            in_content = pattern.search(content)
            if in_content is not None:
                yield item, label, in_content.group(0)


def _project(root: Path) -> dict[str, object]:
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_no_tracked_file_carries_a_placeholder_or_a_retired_name() -> None:
    """Article 0: every occurrence is replaced, and none has come back."""
    tracked = _tracked_files(REPOSITORY)
    # Anti-vacuity floor: an enumeration that found nothing cannot pass.
    assert len(tracked) >= 10, tracked
    assert sorted(set(occurrences(REPOSITORY))) == []


def test_the_distribution_and_the_command_carry_the_decided_name() -> None:
    """Article 0: what replaced the placeholder is asserted where it must appear.

    A guard that only forbids proves nothing about what replaced the placeholder,
    so the decided name is required at the two places a user meets it: the
    distribution they install and the command they type. `sf-` is refused by name
    because the operator retired that prefix — `sf` is another project's command.
    """
    project = _project(REPOSITORY)
    name = project["name"]
    scripts = project["scripts"]
    assert isinstance(name, str) and isinstance(scripts, dict)
    assert name == DECIDED_NAME or name.startswith(f"{DECIDED_NAME}-"), name
    assert set(scripts) == {DECIDED_NAME}, scripts
    assert not name.startswith("sf-"), name
    assert (REPOSITORY / "src" / f"{DECIDED_NAME}_cli").is_dir()


def test_the_guard_catches_each_spelling_it_exists_to_catch(tmp_path: Path) -> None:
    """Article 0: the guard is proven against a planted occurrence of each shape.

    One planted file at a time, in a tree of its own, so that a passing run can
    say which shape it would have caught rather than that something matched.
    """
    planted = tmp_path / "planted.md"
    rendered_placeholders = [
        text
        for character in ("-", "_")
        for text in (
            "oss" + character + "brand",
            "<" + "oss" + character + "brand" + ">",
            ("oss" + character + "brand").upper(),
        )
    ]
    for text in rendered_placeholders:
        planted.write_text(f"The prefix is {text} here.\n", encoding="utf-8")
        assert list(occurrences(tmp_path)) == [(Path("planted.md"), "placeholder", text)], text

    for text in (_RETIRED_CANDIDATE, f"{_RETIRED_CANDIDATE}-cli", f"{_RETIRED_CANDIDATE}_cli"):
        planted.write_text(f"Installed as {text} once.\n", encoding="utf-8")
        found = list(occurrences(tmp_path))
        assert [item[1] for item in found] == ["retired candidate"], (text, found)

    # The exact defect a blanket substring replacement produced in this project.
    for text in (f"{DECIDED_NAME}ory", f"{DECIDED_NAME}Ory"):
        planted.write_text(f"This field is {text}.\n", encoding="utf-8")
        found = list(occurrences(tmp_path))
        assert [item[1] for item in found] == ["the decided name glued into a word"], (text, found)

    # The operator surface's own name is a word and is admitted; the same stem
    # running on into a longer word is the defect again and is not.
    operator = DECIDED_NAME + _OPERATOR_SUFFIX
    for text in (f"{operator} status", f"`{operator}`", f"{operator}."):
        planted.write_text(f"Type {text}\n", encoding="utf-8")
        assert list(occurrences(tmp_path)) == [], text
    for text in (f"{operator}aemon", f"{operator}x"):
        planted.write_text(f"Type {text} here.\n", encoding="utf-8")
        found = list(occurrences(tmp_path))
        assert [item[1] for item in found] == ["the decided name glued into a word"], (text, found)

    planted.unlink()
    at_path = tmp_path / "src" / ("oss" + "_" + "brand" + "_cli")
    at_path.mkdir(parents=True)
    (at_path / "__init__.py").write_text("", encoding="utf-8")
    assert [item[0] for item in occurrences(tmp_path)] == [
        Path("src") / ("oss" + "_" + "brand" + "_cli") / "__init__.py"
    ]
    shutil.rmtree(tmp_path / "src")


def test_the_guard_does_not_fire_on_the_words_the_accident_damaged(tmp_path: Path) -> None:
    """The English words a blanket replacement once mangled are not occurrences.

    A guard for a retired name that also fires on "mandatory" would be turned off
    within a week, and a guard nobody runs holds nothing (article 2). The words
    that were actually damaged are the ones asserted innocent.
    """
    planted = tmp_path / "innocent.md"
    innocent = "Reading the diff is mandatory; the review mandates it, and it was mandated."
    planted.write_text(f"{innocent}\nThe command is {DECIDED_NAME}, from {DECIDED_NAME}-cli.\n")
    assert list(occurrences(tmp_path)) == []
