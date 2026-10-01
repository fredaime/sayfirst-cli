# SPDX-License-Identifier: Apache-2.0
"""The rules of the umbrella's install check, with the defect planted against each.

`scripts/check_umbrella_install.py` measures these rules on a real install;
this file proves each rule catches what it exists to catch, without installing
anything. Both read the same functions, so there is no second copy to drift.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

from pathlib import Path

import check_umbrella_install as guard

WHOLE = sorted(guard.EXPECTED_CLOSURE)

#: What the four distributions declare today, as an installed environment
#: reports it. The real comparison is made by the gate on a real install; this
#: is the shape the rule is planted against.
DECLARED = {
    "sayfirst": {
        "sayfirst": "sayfirst_cli.main:run",
        "sayfirst-daemon": "sayfirst_quickstart.command:main",
        "sayfirstd": "sayfirstd.main:run",
    },
    "sayfirst-cli": {"sayfirst": "sayfirst_cli.main:run"},
    "sayfirst-control-plane": {"sayfirst-daemon": "sayfirst_quickstart.command:main"},
    "sayfirstd": {"sayfirstd": "sayfirstd.main:run"},
    "sayfirst-contract": {},
    "sayfirst-boundary": {},
}


def _with(distribution: str, scripts: dict[str, str]) -> dict[str, dict[str, str]]:
    """A copy of the real declarations with one distribution's scripts replaced."""
    return {**DECLARED, distribution: scripts}


def test_the_whole_product_is_six_distributions_of_this_project() -> None:
    """The positive rule, spelled once here so that a seventh name is a diff."""
    assert set(guard.EXPECTED_CLOSURE) == {
        "sayfirst",
        "sayfirst-cli",
        "sayfirst-control-plane",
        "sayfirstd",
        "sayfirst-contract",
        "sayfirst-boundary",
    }
    assert guard.closure_failures(WHOLE) == []


def test_a_planted_seventh_distribution_fails_the_closure() -> None:
    """WATCHED FIRING. Anything the product does not name is a failure, whatever it is."""
    reported = guard.closure_failures([*WHOLE, "starlette"])
    assert reported == [
        "the install brought distributions the product does not name: ['starlette']"
    ]


def test_a_missing_owner_fails_the_closure_and_is_named() -> None:
    """WATCHED FIRING. A product that arrives without its daemon is not whole."""
    without = [name for name in WHOLE if name != "sayfirst-control-plane"]
    reported = guard.closure_failures(without)
    assert reported == [
        "the install did not bring ['sayfirst-control-plane']: the product is not whole"
    ]


def test_an_empty_closure_is_a_failure_and_never_a_pass() -> None:
    """ANTI-VACUITY. An install that did not happen has no extra distribution either."""
    reported = guard.closure_failures([])
    assert reported[0] == "the closure does not contain sayfirst: nothing was installed"


def test_a_name_spelled_another_way_is_the_same_name() -> None:
    """A closure is compared the way an index compares names (PEP 503)."""
    respelled = ["SayFirst", "sayfirst_cli", "sayfirst.control.plane", "SAYFIRSTD"]
    assert guard.closure_failures([*respelled, "sayfirst_contract", "sayfirst_boundary"]) == []


def test_the_declarations_as_they_stand_are_mirrors() -> None:
    assert guard.mirror_failures(DECLARED) == []


def test_a_mirror_that_drifted_from_its_owner_is_named_with_both_targets() -> None:
    """WATCHED FIRING. The owner moved its entry point and the umbrella did not follow."""
    moved = _with("sayfirstd", {"sayfirstd": "sayfirstd.cli:main"})
    assert guard.mirror_failures(moved) == [
        "'sayfirstd': the umbrella points at 'sayfirstd.main:run' "
        "and sayfirstd declares 'sayfirstd.cli:main'"
    ]


def test_an_owner_that_no_longer_declares_its_command_is_named() -> None:
    """WATCHED FIRING. The umbrella would point a command at a module nobody promises."""
    dropped = _with("sayfirst-control-plane", {})
    assert guard.mirror_failures(dropped) == [
        "sayfirst-control-plane declares no command 'sayfirst-daemon' for the umbrella to mirror"
    ]


def test_a_command_the_umbrella_does_not_name_is_named() -> None:
    """WATCHED FIRING. One install line has to yield all three commands."""
    two = {name: target for name, target in DECLARED["sayfirst"].items() if name != "sayfirstd"}
    assert guard.mirror_failures(_with("sayfirst", two)) == [
        "the umbrella does not name 'sayfirstd', which sayfirstd declares"
    ]


def test_a_command_no_distribution_owns_is_refused() -> None:
    """WATCHED FIRING. The umbrella has no code to point a command of its own at."""
    extra = {**DECLARED["sayfirst"], "sayfirst-extra": "sayfirst_cli.main:run"}
    assert guard.mirror_failures(_with("sayfirst", extra)) == [
        "the umbrella declares commands no distribution owns: ['sayfirst-extra']"
    ]


def test_an_environment_reporting_names_another_way_is_read_the_same() -> None:
    """Installed metadata spells a name as its project file did; the rule does not care."""
    respelled = {name.replace("-", "_").upper(): scripts for name, scripts in DECLARED.items()}
    assert guard.mirror_failures(respelled) == []


def _executable(directory: Path, name: str, script: str) -> None:
    """A stand-in for an installed command: a shell script that does what the test says."""
    path = directory / name
    path.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    path.chmod(0o755)


def test_three_commands_that_start_report_nothing(tmp_path: Path) -> None:
    for command in guard.OWNERS:
        _executable(tmp_path, command, "exit 0")
    assert guard.command_failures(tmp_path) == []


def test_a_command_the_install_did_not_leave_is_named(tmp_path: Path) -> None:
    """WATCHED FIRING. An entry point the installer skipped is a command a reader cannot type."""
    for command in ("sayfirst", "sayfirstd"):
        _executable(tmp_path, command, "exit 0")
    assert guard.command_failures(tmp_path) == [
        "the install left no sayfirst-daemon beside its interpreter"
    ]


def test_a_command_that_does_not_start_is_named_with_its_last_word(tmp_path: Path) -> None:
    """WATCHED FIRING. A mirror pointing at a module that is gone installs, and then fails here."""
    for command in ("sayfirst", "sayfirst-daemon"):
        _executable(tmp_path, command, "exit 0")
    _executable(
        tmp_path,
        "sayfirstd",
        'echo "Traceback (most recent call last):" >&2\n'
        "echo \"ModuleNotFoundError: No module named 'sayfirstd'\" >&2\n"
        "exit 1",
    )
    assert guard.command_failures(tmp_path) == [
        "sayfirstd --help answered 1: ModuleNotFoundError: No module named 'sayfirstd'"
    ]


def test_a_command_that_fails_in_silence_is_still_named(tmp_path: Path) -> None:
    """WATCHED FIRING. No word on the error stream is said, not left as an empty tail."""
    for command in ("sayfirst-daemon", "sayfirstd"):
        _executable(tmp_path, command, "exit 0")
    _executable(tmp_path, "sayfirst", "exit 3")
    assert guard.command_failures(tmp_path) == [
        "sayfirst --help answered 3: nothing on its error stream"
    ]
