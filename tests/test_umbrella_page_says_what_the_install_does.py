# SPDX-License-Identifier: Apache-2.0
"""The umbrella's index page is held to what the install check measures.

`umbrella/README.md` is what a reader sees on the index before installing
anything. Three of its statements are facts the gate measures elsewhere, and a
page that states them a second time is a page that can drift from them:

* which command comes from which distribution — `OWNERS`, in
  `scripts/check_umbrella_install.py`;
* what removing the product whole removes — `EXPECTED_CLOSURE`, in the same
  file: every distribution the install brought, and no other;
* how a reader who installed the three commands as the tool `sayfirst-cli`
  arrives here — `uv` refuses to overwrite a command another tool owns, so the
  page has to name the removal before the install.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import re

import check_umbrella_install as guard

PAGE = guard.UMBRELLA / "README.md"

#: A row of the page's table: a command, what it is, the distribution that owns it.
_ROW = re.compile(r"^\| `([a-z-]+)` \| .* \| `([a-z-]+)` \|$", re.MULTILINE)

#: The line that removes the product whole from an environment a reader owns.
_REMOVAL = re.compile(r"^\$ pip uninstall (.+)$", re.MULTILINE)


def owners_on_the_page(page: str) -> dict[str, str]:
    """Each command the page's table names, and the distribution it says owns it."""
    return dict(_ROW.findall(page))


def removed_whole(page: str) -> list[list[str]]:
    """The distributions each `pip uninstall` line of the page names."""
    return [found.split() for found in _REMOVAL.findall(page)]


def arrives_after_removing(page: str, old_tool: str) -> bool:
    """Whether the page removes the old tool on a line before a line that installs this one."""
    lines = page.splitlines()
    removal = f"$ uv tool uninstall {old_tool}"
    install = f"$ uv tool install {guard.UMBRELLA_NAME}"
    return any(
        line == removal and install in lines[number + 1 :] for number, line in enumerate(lines)
    )


def test_the_table_names_each_command_and_its_owner() -> None:
    assert owners_on_the_page(PAGE.read_text(encoding="utf-8")) == dict(guard.OWNERS)


def test_removing_the_product_whole_names_everything_the_install_brought() -> None:
    lines = removed_whole(PAGE.read_text(encoding="utf-8"))
    assert len(lines) == 1, lines
    assert sorted(lines[0]) == sorted(guard.EXPECTED_CLOSURE)


def test_the_page_removes_the_earlier_tool_before_installing_this_one() -> None:
    assert arrives_after_removing(PAGE.read_text(encoding="utf-8"), "sayfirst-cli")


def test_the_three_tools_line_is_read_before_the_block_it_changes() -> None:
    """A reader runs a console block before reading under it: the variant comes first."""
    page = PAGE.read_text(encoding="utf-8")
    variant = "uv tool uninstall " + " ".join(sorted(set(guard.OWNERS.values())))
    assert variant in page, variant
    assert page.index(variant) < page.index("$ uv tool uninstall sayfirst-cli\n")


def test_a_table_that_gives_a_command_to_the_wrong_owner_is_caught() -> None:
    """WATCHED FIRING."""
    page = PAGE.read_text(encoding="utf-8").replace(
        "| `sayfirst-control-plane` |", "| `sayfirstd` |"
    )
    assert owners_on_the_page(page)["sayfirst-daemon"] == "sayfirstd"
    assert owners_on_the_page(page) != dict(guard.OWNERS)


def test_a_removal_line_that_forgets_a_distribution_is_caught() -> None:
    """WATCHED FIRING. A line that leaves the boundary behind does not remove the product whole."""
    page = PAGE.read_text(encoding="utf-8").replace(" sayfirst-boundary", "")
    assert sorted(removed_whole(page)[0]) != sorted(guard.EXPECTED_CLOSURE)


def test_a_page_that_installs_before_it_removes_is_caught() -> None:
    """WATCHED FIRING. The order is the instruction: the other order is the error `uv` prints."""
    page = "$ uv tool install sayfirst\n$ uv tool uninstall sayfirst-cli\n"
    assert not arrives_after_removing(page, "sayfirst-cli")
    assert arrives_after_removing(
        "$ uv tool uninstall sayfirst-cli\n$ uv tool install sayfirst\n", "sayfirst-cli"
    )
