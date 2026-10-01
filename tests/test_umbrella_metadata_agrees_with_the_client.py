# SPDX-License-Identifier: Apache-2.0
"""The umbrella's index page says what the client's says, wherever both say it.

Two project files in one repository are two places to state the interpreters
admitted, the licence, the author and the repository a reader is sent to. The
umbrella installs the client, so a page that admits an interpreter the client
refuses is a page that offers an install which then fails; and a second author
or a second repository on the project's most visible name is a claim nobody
decided to make.

The umbrella has no guard of its own for these: it is held to the client's
project file, which the client's own guards hold.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from test_pointers_survive_publication import PUBLIC_CLIENT, project_urls

REPOSITORY = Path(__file__).resolve().parents[1]
UMBRELLA = REPOSITORY / "umbrella"

#: What the two project tables state identically.
SHARED = ("requires-python", "license", "authors", "classifiers", "version")


def _project(directory: Path) -> dict[str, object]:
    return tomllib.loads((directory / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def disagreements(umbrella: dict[str, object], client: dict[str, object]) -> list[str]:
    """Every shared key on which the two project tables differ."""
    return [key for key in SHARED if umbrella.get(key) != client.get(key)]


def test_the_two_project_files_agree_wherever_both_speak() -> None:
    client = _project(REPOSITORY)
    # Anti-vacuity floor: two tables that both lack a key agree about nothing.
    for key in SHARED:
        assert client.get(key), key
    assert disagreements(_project(UMBRELLA), client) == []


def test_the_rule_fires_on_an_interpreter_the_client_does_not_admit() -> None:
    """WATCHED FIRING."""
    client = _project(REPOSITORY)
    widened = {**_project(UMBRELLA), "requires-python": ">=3.10,<3.15"}
    assert disagreements(widened, client) == ["requires-python"]


def test_the_umbrella_is_named_for_the_decided_name_and_nothing_else() -> None:
    """Article 0: the name of the product, as a distribution, is the decided name itself."""
    assert _project(UMBRELLA)["name"] == "sayfirst"
    assert _project(REPOSITORY)["name"] == "sayfirst-cli"


def test_every_url_of_the_umbrella_is_this_public_repository() -> None:
    """The same repository as the client's, and a page that exists in this tree."""
    urls = project_urls(UMBRELLA)
    client = project_urls(REPOSITORY)
    assert set(urls) == set(client), urls
    assert urls["Repository"] == client["Repository"] == PUBLIC_CLIENT
    assert urls["Changelog"] == client["Changelog"]
    page = urls["Documentation"].removeprefix(f"{PUBLIC_CLIENT}/blob/main/")
    assert page == "umbrella/README.md", urls["Documentation"]
    assert (REPOSITORY / page).is_file(), page


@pytest.mark.parametrize("key", ["description", "readme"])
def test_the_umbrella_states_its_own_page(key: str) -> None:
    """What is NOT shared: its one-line description and its own README."""
    umbrella, client = _project(UMBRELLA), _project(REPOSITORY)
    assert umbrella.get(key), key
    if key == "description":
        assert umbrella[key] != client[key]
    else:
        assert (UMBRELLA / str(umbrella[key])).is_file()
