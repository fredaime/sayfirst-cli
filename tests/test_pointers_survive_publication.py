# SPDX-License-Identifier: Apache-2.0
"""No reader-facing document links to the repository that is never published,
and every address a package page offers is a public one.

The open control plane is published as a repository **created fresh**: article 0
offers that path or a review of the existing record, and the control plane's
`SECURITY.md` records that the second path was closed by measurement — a
pre-redaction object survives in a pull-request reference that no rewrite
reaches. So `sf-control-plane-lt` never becomes public.

This repository adopts that constitution *by pointer* (article 0: never by copy,
because a copy drifts). On 2026-09-14 both of its pointers named that
never-public repository — `README.md` linked to its `CONSTITUTION.md` on
github.com, and `NOTICE` sent a reader to "the TRADEMARKS.md of the control
plane repository". Each would have resolved for nobody from the first public
minute, in the two documents an outsider reads first, and nothing would have
said so: a dead link is not a failing test.

The rule therefore constrains the OPERATION, not the name. It is not "do not
mention `sf-control-plane-lt`" — the gate must still say which sibling checkout
it reads (`SAYFIRST_CONTRACT_SOURCE=../sf-control-plane-lt`), and a local
directory path is not a claim that a reader can open a page. What is refused is
a **URL** to it: the form that promises a reader somewhere to go.

The URL is written in the same act that creates the public repository. Until
then this guard is what keeps the promise from being made early.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]

#: The repository the project has decided never to publish. Named once, here,
#: so a reader of this file can see what the rule is about; every other use in
#: this module derives from this constant rather than repeating the spelling.
NEVER_PUBLISHED = "sf-control-plane-lt"

#: A hyperlink to a hosting platform, in any of the forms these documents use:
#: a bare URL, a Markdown link target, an autolink. The scheme is what makes it
#: a promise that something is reachable, so the scheme is what this matches —
#: a bare path such as `../sf-control-plane-lt` is deliberately outside it.
_URL = re.compile(r"https?://[^\s)>\]\"']+")


def _reader_facing() -> list[Path]:
    """Every document a person outside the project reads.

    Walked, never enumerated: a governance file added next month is covered
    without anyone remembering to add it here. Test sources are excluded — this
    module has to be able to name the thing it forbids.
    """
    found = [path for path in sorted(REPOSITORY.glob("*.md")) if path.is_file()]
    found += [path for path in sorted(REPOSITORY.glob("docs/**/*.md")) if path.is_file()]
    notice = REPOSITORY / "NOTICE"
    if notice.is_file():
        found.append(notice)
    return found


DOCUMENTS = _reader_facing()


def test_the_walk_finds_the_documents_this_rule_is_about() -> None:
    """ANTI-VACUITY. A glob that matched nothing would make every assertion
    below pass by absence, which is the failure mode this project has met
    often enough to have a standing rule against it."""
    names = {path.name for path in DOCUMENTS}
    assert len(DOCUMENTS) >= 4, f"only {len(DOCUMENTS)} reader-facing documents found"
    for required in ("README.md", "NOTICE", "SECURITY.md", "TRADEMARKS.md"):
        assert required in names, f"{required} is not being scanned by this rule"


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda p: p.name)
def test_no_reader_facing_link_points_at_the_unpublished_repository(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    offenders = [url for url in _URL.findall(text) if NEVER_PUBLISHED in url]
    assert not offenders, (
        f"{path.relative_to(REPOSITORY)} links to {NEVER_PUBLISHED}, which article 0's "
        f"fresh-repository path means is never made public: {offenders}. A reader outside "
        f"the project cannot open it. Name the repository without a URL until the public "
        f"one exists, and write the URL in the act that creates it."
    )


def test_the_rule_fires_on_the_link_that_actually_stood_here() -> None:
    """WATCHED FIRING, on the exact text `README.md` carried until 2026-09-14.

    A rule whose only evidence is that it currently passes is a rule that would
    also pass if it had stopped applying.
    """
    historical = (
        "[`CONSTITUTION.md`]"
        f"(https://github.com/fredaime/{NEVER_PUBLISHED}/blob/main/CONSTITUTION.md)"
    )
    assert [url for url in _URL.findall(historical) if NEVER_PUBLISHED in url]


def test_the_rule_leaves_a_local_sibling_path_alone() -> None:
    """WATCHED NOT FIRING. The gate documents the checkout it reads, and must
    keep being able to: a detector that flagged every mention of the name would
    pass the probe above and mean nothing."""
    gate_line = f"$ SAYFIRST_CONTRACT_SOURCE=../{NEVER_PUBLISHED} ./scripts/gate.sh"
    assert not [url for url in _URL.findall(gate_line) if NEVER_PUBLISHED in url]


#: The two public repositories, decided by the operator. Every URL this project
#: publishes about itself points at one of them. They do not exist yet; that is
#: the point of writing them down before the act that creates them, so the act
#: has one name to check rather than a search to make.
PUBLIC_CONTROL_PLANE = "https://github.com/fredaime/sayfirst-control-plane"
PUBLIC_CLIENT = "https://github.com/fredaime/sayfirst-cli"


def project_urls(root: Path) -> dict[str, str]:
    """The `[project.urls]` table of the distribution at `root`, or an empty one."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return dict(project.get("urls") or {})


def test_every_published_url_of_this_distribution_is_a_public_repository() -> None:
    """A package page is read by people who hold nothing of this project.

    `[project.urls]` is the one place a distribution sends a stranger, and it is
    rendered on the index page before anybody installs anything. A URL there to
    a repository that is never made public is the same broken promise this
    module already refuses in `README.md` and `NOTICE`, made to a wider audience.
    """
    urls = project_urls(REPOSITORY)
    assert set(urls) == {"Repository", "Documentation", "Changelog"}, urls
    for name, url in urls.items():
        assert url.startswith(PUBLIC_CLIENT), (name, url)
        assert NEVER_PUBLISHED not in url, (name, url)


def test_the_url_rule_fires_on_a_pointer_to_the_repository_that_is_never_published(
    tmp_path: Path,
) -> None:
    """WATCHED FIRING, through the same reader the real distribution is read
    through: a project file whose page would send a stranger to the repository
    that is never published. A rule whose only evidence is that it passes today
    would also pass if it had stopped applying."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "planted"\nversion = "0.0.0"\n'
        "[project.urls]\n"
        f'Repository = "https://github.com/fredaime/{NEVER_PUBLISHED}"\n',
        encoding="utf-8",
    )
    urls = project_urls(tmp_path)
    assert urls, "the reader saw no table: the probe proves nothing"
    assert not all(url.startswith(PUBLIC_CLIENT) for url in urls.values())
    assert any(NEVER_PUBLISHED in url for url in urls.values())
