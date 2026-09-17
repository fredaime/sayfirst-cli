# SPDX-License-Identifier: Apache-2.0
"""Article 14 at repository scope: what ships names no record this project keeps private.

Article 14's rule is that "nothing in this repository imports, names, links to
or is shaped by a private product: no private symbol, path, vocabulary or
roadmap appears here", and its reason is that "a dependency pointing the wrong
way is a leak that cannot be unpublished". Article 0 makes this repository
public, so every tracked file's content is the thing
that gets published, and a docstring is as published as a paragraph of
`README.md`.

**What this refuses is the INDEX, not the word.** « A review found this », « the
fix was », « the finding was » are facts about the code: they say how a rule came
to be known, and a reader outside the project can check every one of them against
the code beside them. Attach a number and the same sentence stops being a fact
and becomes a pointer: it tells a reader to go and open a document nobody
outside the project can open, and tells them nothing about the behaviour. So the
rule is the index, and every detector below wants one; a sentence naming a
review, a fix or a finding without one is allowed and stays. The sweep that
installed this guard therefore reworded each reference to the fact it was
reaching for rather than deleting the sentence. No example of the construction
is written out here, for the reason the work-item comment gives below.

**The detectors are structural.** They match the constructions by which a
private record enters a public file — a numbered work item, a ruling number, a
planning document's file name, a repository named as private, an abbreviated
commit — never a list of the records themselves. A deny-list of private words is
itself the leak it is meant to prevent.

**This repository's own labels are not refused.** `docs/PARTITION.md` defines
its questions and publishes both the question and the answer, so a sentence
citing one sends a reader to a document they hold. What is refused is a label of
a record that is nowhere in this tree — which is why the decision-label detector
below wants a letter and a digit, the shape those records use, and leaves the
published family alone.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import ast
import io
import re
import shutil
import subprocess
import tokenize
from collections.abc import Iterator
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

#: What this repository publishes and this guard therefore reads: the client, the
#: convenience packs it ships inside it, its tests, its documents, its governance
#: files, its manifest, the scripts a reader runs and the workflow that runs
#: them. Named as roots rather than as a file list, so a document added next
#: month is covered without anyone remembering to add it here.
#:
#: The last six joined after a hand check found nothing in them: they are
#: tracked, they become public with the repository, and the guard was not
#: reading them — a latent gap rather than a leak, and the difference between
#: the two is only ever one commit. `LICENSE` is deliberately outside it: it is
#: a notice rather than a work, which is the same exception article 15 makes.
#: The changelog is one more: a release note is read by every person deciding
#: whether to upgrade, and it is as published as `README.md`.
#:
#: WHAT IS READ OF EACH FILE UNDER THESE ROOTS, per suffix, because a root read
#: in part is not a root read. Every detector in `EVERYWHERE` reads every one of
#: these files whole, whatever its suffix. The detectors in `PROSE_ONLY` read
#: the sentences a file publishes, and `prose_of` below decides what those are:
#: a `.md`, `.rst` or `.txt` file, and `NOTICE`, whole; a `.py` file's comments
#: and docstrings; the `#` comment lines of a `.yml`, `.yaml`, `.toml` or `.sh`
#: file; and of anything else, nothing. The workflows and the scripts are in
#: that last group on purpose rather than by omission: a workflow and a shell
#: script argue their rules in comments the way a module argues them in a
#: docstring — this repository's release workflow carries pages of them — while
#: the lines around those comments pin actions, build identifiers and match
#: patterns, which is a program's ordinary business and not a sentence.
PUBLISHED_ROOTS = (
    "src",
    "tests",
    "docs",
    "scripts",
    ".github/workflows",
    "README.md",
    "NOTICE",
    "SECURITY.md",
    "TRADEMARKS.md",
    "pyproject.toml",
    "CHANGELOG.md",
)

#: Suffixes whose whole content is prose.
PROSE_SUFFIXES = frozenset({".md", ".rst", ".txt"})

#: Suffixes whose `#` comment lines are prose and whose other lines are not. A
#: workflow, a project file and a shell script argue their rules in comments —
#: this repository's release workflow does it at length — and a guard that read
#: none of them would leave the prose written at release time unread, which is
#: where a private reference is most likely to be reached for. What the comments
#: sit among is a program: a pinned action, a `sed` expression, an identifier a
#: script builds.
COMMENT_SUFFIXES = frozenset({".yml", ".yaml", ".toml", ".sh"})

#: Files that are prose and carry no suffix to say so. `NOTICE` is a document a
#: reader reads, and a guard that judged it by its extension would read the one
#: file most likely to name an origin as if it were a program.
PROSE_NAMES = frozenset({"NOTICE"})

#: Directories an enumeration without a version-control listing must not enter.
NOT_PUBLISHED = frozenset(
    {".venv", ".venv-reduced", ".wheelhouse", "__pycache__", ".ruff_cache", ".pytest_cache"}
)

#: A work item of a tracker this repository does not publish: a numbered task, a
#: review finding, a round of fixes, an epic. The NUMBER is what makes it a
#: pointer — « a review found this » is a fact about the code, while the same
#: sentence with an index attached sends a reader to a document they cannot
#: open. This comment carries no example, because an example of the construction
#: inside the guard would be an occurrence of it.
WORK_ITEM = re.compile(
    r"\b(?:task|finding|epic|ticket|fix\s+round|round\s+of\s+fixes)\s*[-_#]?\s*\d+",
    re.IGNORECASE,
)

#: A ruling of a decision record this repository does not publish. The articles
#: of the constitution it adopts by pointer are deliberately outside it: those
#: are cited as « article N », in words, and that spelling is public.
RULING = re.compile(r"\bR\d{1,3}\b|\bLT-\d{2,3}\b")

#: A planning document by file name. `manifest` is a domain word here — a pack
#: declares one — so it is not in the list; what is listed is the shape the name
#: of a planning artefact takes.
PLANNING_DOCUMENT = re.compile(
    r"\b[A-Za-z0-9_-]*(?:report|brief|backlog|roadmap|plan)\.md\b", re.IGNORECASE
)

#: A decision or doctrine of a record this repository does not hold, cited by its
#: label. A letter and a digit is the shape those labels take; this repository's
#: own published questions carry no digit and are untouched.
DECISION_LABEL = re.compile(r"\b(?:decision|doctrine)\b(?:\s+[a-z]+){0,2}\s+\(?[A-Z]\d{1,2}\)?\b")

#: A non-public source attributed by name: the construction by which a private
#: repository's name enters a public sentence. Naming the OPEN sibling is not
#: that — the gate has to say which checkout it reads — so the pattern wants the
#: word that claims the source is not public.
NAMED_NON_PUBLIC_SOURCE = re.compile(
    r"\b(?:private|parent|internal|upstream|proprietary|closed)"
    r"(?:\s+[a-z-]+){0,3}\s+(?:repository|product|source|tree|client)\s+"
    r"(?:named|called)\s+[A-Za-z0-9_.-]+",
    re.IGNORECASE,
)

#: An abbreviated commit identifier. At least one digit is required, because
#: English is written in the same alphabet: « succeeded » carries seven
#: characters a bare hexadecimal pattern reads as an object name.
COMMIT_IN_PROSE = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*\d)[0-9a-f]{7,40}(?![0-9A-Za-z])")

#: Detectors that read every published file, code and prose alike.
EVERYWHERE = {
    "numbered work item": WORK_ITEM,
    "ruling number": RULING,
    "planning document": PLANNING_DOCUMENT,
    "decision label this repository does not define": DECISION_LABEL,
    "non-public source named outright": NAMED_NON_PUBLIC_SOURCE,
}

#: Detectors that read prose only. Code pins digests and builds identifiers as
#: its ordinary business; a sentence does neither.
PROSE_ONLY = {"commit identifier in prose": COMMIT_IN_PROSE}


def _published_files(root: Path) -> list[Path]:
    """Every file this repository publishes under the roots above.

    The listing and the walk are unioned rather than chosen between: a file
    added and not yet committed is published the moment it is, and a guard that
    read only what was already recorded would pass on the change that adds a
    leak and fail on the one after it.
    """
    found = set(_walked(root))
    if (root / ".git").exists() and shutil.which("git") is not None:
        listed = subprocess.run(
            ("git", "ls-files", "-z", *PUBLISHED_ROOTS),
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        found.update(Path(name) for name in listed.split("\0") if name)
    return sorted(item for item in found if (root / item).is_file())


def _walked(root: Path) -> list[Path]:
    found: list[Path] = []
    for named in PUBLISHED_ROOTS:
        start = root / named
        if start.is_file():
            found.append(Path(named))
            continue
        found.extend(
            item.relative_to(root)
            for item in start.rglob("*")
            if item.is_file() and not NOT_PUBLISHED & set(item.relative_to(root).parts)
        )
    return sorted(found)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def prose_of(path: Path, content: str) -> str:
    """The sentences a file publishes: a prose file whole, a module's comments and
    docstrings, a workflow's or a script's comment lines, and nothing a program
    merely computes with.

    Python is where this repository keeps most of its prose — every rule it holds
    is argued in a docstring — so a guard that read only `.md` would leave the
    larger half of what ships unread. The workflows, the project file and the
    scripts keep the rest, in `#` comments, and they are read the same way and
    for the same reason: the alternative is a root the guard enumerates and does
    not read. It is also why a string a program computes with is left out: those
    carry digests and fixtures, and reading them as sentences is how a guard
    starts firing on the evidence vectors.
    """
    if path.suffix in PROSE_SUFFIXES or path.name in PROSE_NAMES:
        return content
    if path.suffix in COMMENT_SUFFIXES:
        return "\n".join(line for line in content.splitlines() if line.lstrip().startswith("#"))
    if path.suffix != ".py":
        return ""
    said: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(content).readline):
            if token.type == tokenize.COMMENT:
                said.append(token.string)
        tree = ast.parse(content)
    except (SyntaxError, tokenize.TokenError, IndentationError, ValueError):
        return "\n".join(said)
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            docstring = ast.get_docstring(node, clean=False)
            if docstring:
                said.append(docstring)
    return "\n".join(said)


def public_vocabulary(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (file, class) for every private-record reference this repository publishes."""
    for item in _published_files(root):
        content = _read(root / item)
        if content is None:
            continue
        for category, pattern in EVERYWHERE.items():
            if pattern.search(content):
                yield item, category
        prose = prose_of(item, content)
        for category, pattern in PROSE_ONLY.items():
            if prose and pattern.search(prose):
                yield item, category


def test_nothing_this_repository_publishes_names_a_record_it_keeps_private() -> None:
    """Article 14: every published sentence sends a reader somewhere they can go."""
    published = _published_files(REPOSITORY)
    # Anti-vacuity floor: an enumeration that found nothing cannot pass, and one
    # that found only documents would leave every docstring unread.
    assert len(published) >= 40, published
    assert [item for item in published if item.suffix in PROSE_SUFFIXES]
    assert [item for item in published if item.suffix == ".py"]
    # Every root actually reaches a file. A root spelled wrongly, or one dropped
    # from the tuple, makes this guard quietly smaller — which is the shape the
    # widening was for, so it is held rather than trusted.
    reached = {item.as_posix() for item in published}
    for root in PUBLISHED_ROOTS:
        assert any(name == root or name.startswith(f"{root}/") for name in reached), root
    assert sorted(set(public_vocabulary(REPOSITORY))) == []


def test_the_guard_catches_a_planted_example_of_every_shape(tmp_path: Path) -> None:
    """The rule is proven against a planted example of each class it refuses.

    Every example is invented. Reproducing a real private reference in order to
    test for it would publish it, which is the defect this guard is for.
    """
    planted = tmp_path / "README.md"
    cases = {
        "numbered work item": "Closes " + "finding" + " 3 of the review.",
        "ruling number": "The requirement is " + "R" + "46, which overrides the letter.",
        "planning document": "The disagreement is recorded in " + "example-9-report" + ".md.",
        "decision label this repository does not define": (
            "The name was settled by " + "decision" + " Z9."
        ),
        "non-public source named outright": (
            "A " + "private source repository " + "named" + " example-internal holds it."
        ),
        "commit identifier in prose": "Fixed at commit " + "1a2b3c4" + " on that branch.",
    }
    for category, content in cases.items():
        planted.write_text(content, encoding="utf-8")
        found = {category for _, category in public_vocabulary(tmp_path)}
        assert category in found, (category, content, found)


def test_the_guard_reads_a_docstring_and_leaves_a_pinned_digest_alone(tmp_path: Path) -> None:
    """Two things at once, because each would pass without the other.

    A commit named in a MODULE's own prose is as published as one named in a
    document, and a guard that read only `.md` would have missed every one this
    repository's own sweep found. A sixty-four character digest a test pins is
    not a commit and must not be read as one, or the guard would fire on the
    published evidence vectors themselves.
    """
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        '"""A module whose docstring names commit ' + "1a2b3c4" + '."""\n', encoding="utf-8"
    )
    assert ("src/example.py", "commit identifier in prose") in {
        (item.as_posix(), category) for item, category in public_vocabulary(tmp_path)
    }

    source.write_text(
        '"""A module that pins a digest and names no commit."""\n\nDIGEST = "'
        + "0123456789abcdef" * 4
        + '"\n',
        encoding="utf-8",
    )
    assert sorted(set(public_vocabulary(tmp_path))) == []


def test_a_workflow_comment_is_read_as_prose_and_the_lines_around_it_are_not(
    tmp_path: Path,
) -> None:
    """Two things at once, because each would pass without the other.

    A commit named in a workflow's own comment is as published as one named in a
    document, and this repository's release workflow argues its rules in pages of
    them. An action pinned by digest on the line below is a program pinning a
    version, which is a workflow's ordinary business and must not be read as a
    sentence — or the guard would fire on the one construction that makes a
    supply chain reproducible.
    """
    workflow = tmp_path / ".github" / "workflows" / "example.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "# A comment naming commit " + "1a2b3c4" + " of another branch.\non: workflow_dispatch\n",
        encoding="utf-8",
    )
    assert (".github/workflows/example.yml", "commit identifier in prose") in {
        (item.as_posix(), category) for item, category in public_vocabulary(tmp_path)
    }

    workflow.write_text(
        "# A comment that pins an action and names no commit.\n"
        "jobs:\n  one:\n    steps:\n      - uses: example/action@" + "0123456789abcdef" * 2 + "\n",
        encoding="utf-8",
    )
    assert sorted(set(public_vocabulary(tmp_path))) == []


def test_this_repositorys_own_published_questions_are_not_refused(tmp_path: Path) -> None:
    """`docs/PARTITION.md` defines its questions and publishes both halves, so a
    sentence citing one sends a reader to a document they hold. A guard that
    refused them would be asking this repository to stop citing itself."""
    document = tmp_path / "docs" / "PARTITION.md"
    document.parent.mkdir(parents=True)
    document.write_text(
        "**Q-A — Does reading a decision afterwards belong to the client? Closed.**\n"
        "Q-B, Q-C and Q-E remain open; Q-D closed on the same day.\n",
        encoding="utf-8",
    )
    assert sorted(set(public_vocabulary(tmp_path))) == []


def test_the_changelog_is_one_of_the_documents_this_rule_reads() -> None:
    """A release note is published prose. A guard that skipped it would let the
    one document written at release time carry what every other document may not."""
    assert "CHANGELOG.md" in PUBLISHED_ROOTS
    assert Path("CHANGELOG.md") in _published_files(REPOSITORY)
