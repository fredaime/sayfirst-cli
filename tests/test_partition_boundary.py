# SPDX-License-Identifier: Apache-2.0
"""The boundary this repository's README draws, as a test rather than a paragraph.

    "The control plane's own repository keeps **only the operator surface** that
    inspects its daemon — its status, the identity it saw, the plugins it
    composed, the scenarios it replays. Every product command lives here."
                                                       — this repository's README

The operator narrowed that line on 2026-09-05 (Q-A): what travels with the
daemon is what inspects *the daemon's own state*, and reading the evidence the
daemon wrote is a product act. So `trace`, `explain` and `evidence` moved from
the set this file forbids to the set it permits, and the two sets below are the
partition's `here` / `daemon` column in the only form a machine can check.

`docs/PARTITION.md` says the same thing command by command, with the manifest's
reason for each. This file holds the half of it that a machine can check today:
the subcommands this distribution answers are drawn from the set the partition
assigns to the client, and none of them is one the partition leaves with the
daemon. It is written in the positive — what may be here — so that adding a
product command is free and adding an operator command is a red test.

What no test in either repository can see is the *other* repository. The names
`sayfirst` and `sayfirst-cli` were claimed in this tree and in the control
plane's tree at once, and each repository's guard read its own `pyproject.toml`
and passed. The operator settled that on 2026-09-05 — the names are this
repository's, and the control plane renamed its operator surface — so the
collision is closed rather than merely recorded. It was closed by a decision and
not by a test, because no test here could have caught it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sayfirst_cli.instrument import commands as instrument
from sayfirst_cli.main import COMMANDS

REPOSITORY = Path(__file__).resolve().parents[1]
PARTITION_DOC = REPOSITORY / "docs" / "PARTITION.md"

#: The verbs `instrument` answers. Held against the document's own braces below,
#: and against the command's help by
#: `tests/test_instrument_run.py::test_the_help_names_the_three_verbs_and_claims_no_fourth`.
INSTRUMENT_VERBS: frozenset[str] = frozenset({"run", "verify", "apply"})

#: Which of them the partition may say RUN — derived from the command module's
#: own table of verbs that refuse, never written down beside it. A literal here
#: was a pin a future slice had to remember to move: the verb would ship, the
#: row would keep promising a refusal, and this file would keep agreeing with
#: the row. Derived, the slice that lands `apply` turns the row red without
#: anybody having thought about this file.
RUNNING_VERBS: frozenset[str] = INSTRUMENT_VERBS - frozenset(instrument.RESERVED)

#: Commands the partition assigns to this repository — the product surface a
#: user points at their own program (`docs/PARTITION.md`, and the manifest's
#: §3.4 and §3.9). A slice that lands one of these adds it to `main.COMMANDS`.
CLIENT_COMMANDS = frozenset(
    {
        "ask",
        "connect",
        "whoami",
        "profile",
        "packs",
        "integrate",
        "approvals",
        "version",
        # Q-A, closed by the operator on 2026-09-05: the evidence surface
        # crosses. These three are *owed* rather than present — `main.COMMANDS`
        # holds none of them — and they are named here so that the slice that
        # lands them is a green test rather than an edit to this file made under
        # the pressure of a red one.
        "trace",
        "explain",
        "evidence",
        # Article 9: the open project ships the instrumentation engine, its
        # verifier and the convenience packs, and question 3 of the partition
        # names the act — it "points the user's own program at the boundary".
        # `docs/PARTITION.md` had no row for it until this slice; it has one now,
        # so the two documents say the same thing.
        "instrument",
    }
)

#: Commands the partition leaves with the daemon, because they inspect the
#: daemon's *own state* and travel with it. None of them may appear in this
#: distribution. The 2026-09-05 decision narrowed this set rather than the other:
#: reading the evidence a daemon wrote is not inspecting the daemon.
OPERATOR_COMMANDS = frozenset({"status", "doctor", "systems", "policy", "inspect", "halt"})


def test_this_distribution_answers_only_commands_the_partition_gives_it() -> None:
    """Article 14: the product surface is here, and only the product surface."""
    assert set(COMMANDS) <= CLIENT_COMMANDS, sorted(set(COMMANDS) - CLIENT_COMMANDS)
    # Anti-vacuity floor: a dispatch with nothing in it proves nothing.
    assert COMMANDS


def test_no_command_that_inspects_the_daemon_is_answered_here() -> None:
    """The two sets are disjoint, so the first assertion cannot pass vacuously."""
    assert not CLIENT_COMMANDS & OPERATOR_COMMANDS
    assert not set(COMMANDS) & OPERATOR_COMMANDS


def _row_of(command: str) -> list[str]:
    """The partition's row for that command, as its cells.

    Read off the document rather than trusted, because the two halves of this
    repository's claim about what it ships — the dispatch and the partition —
    drifted apart once already: `verify` ran a proof while the row still said
    it was present and refusing.
    """
    for line in PARTITION_DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 3 and command in cells[0]:
            return cells
    raise AssertionError(f"{PARTITION_DOC} has no row whose command names {command!r}")


def _state_of(command: str) -> str:
    """The `State` cell of that row: what the document claims the command does."""
    return _row_of(command)[2]


def _the_partitions_claim(state: str) -> None:
    """Hold one `State` cell against what this distribution does, verb by verb.

    The cell's shape is « <the running verbs> ; <the refusing ones> », and each
    verb is pinned to the side it belongs on. Reading the whole cell for the
    word `verify` would have passed on the sentence this rule exists to catch,
    which named `verify` beside `apply` as present and refusing.

    It is a function rather than a test body because the test below runs THIS
    rule against doctored cells. A companion that re-derived the expression
    would prove that the expression works and nothing about the rule the gate
    actually runs.
    """
    running, _, refusing = state.partition(";")
    assert running, state
    # A refusing half exists exactly while some verb refuses: the day the last
    # one ships, a row still carrying one is as wrong as a row missing one.
    assert bool(refusing) == bool(INSTRUMENT_VERBS - RUNNING_VERBS), state
    for verb in sorted(INSTRUMENT_VERBS):
        side = running if verb in RUNNING_VERBS else refusing
        other = refusing if verb in RUNNING_VERBS else running
        assert f"`{verb}`" in side, (verb, state)
        assert f"`{verb}`" not in other, (verb, state)
    assert "running" in running, state
    assert not refusing or "refusing" in refusing, state


def test_the_partition_says_of_each_instrument_verb_what_this_distribution_does() -> None:
    """The rule, against the document as it stands on the day it runs."""
    _the_partitions_claim(_state_of("instrument"))


def test_the_rows_two_halves_name_the_same_verbs_and_no_fourth() -> None:
    """Anti-vacuity, and the other direction: the row claims no verb that is not there.

    Article 2's rule about a status surface — this document is one — applied to
    the row rather than to the help text. The `Command` cell names the verbs in
    braces and the `State` cell names them in backticks; both are held against
    the table above, which `tests/test_instrument_run.py` holds against the
    command's own help in turn. A verb named here that the command does not
    answer is a claim without evidence.
    """
    cells = _row_of("instrument")
    braced = set(re.findall(r"[a-z]+", cells[0].partition("{")[2].partition("}")[0]))
    assert braced == INSTRUMENT_VERBS, sorted(braced ^ INSTRUMENT_VERBS)
    backticked = set(re.findall(r"`([a-z]+)`", cells[2]))
    assert backticked == INSTRUMENT_VERBS, sorted(backticked ^ INSTRUMENT_VERBS)


@pytest.mark.parametrize(
    "doctored",
    [
        "**`run` running — shipped 2026-09-15**; `apply` and `verify` present and refusing",
        "**`run` and `verify` and `apply` running**; nothing refusing",
        "**`run` and `verify` running**",
        "**`run` and `verify` running**; `apply` present",
    ],
)
def test_the_rule_would_have_failed_on_the_sentence_that_was_there(doctored: str) -> None:
    """The rule watched firing, on the defect it was written for and three neighbours.

    The first is the sentence this repository really carried while `verify` ran
    a proof. The second claims the reserved verb runs. The third drops the
    refusing half, which is what would make the pinning vacuous. The fourth
    keeps both halves and stops saying that the reserved verb refuses.
    """
    with pytest.raises(AssertionError):
        _the_partitions_claim(doctored)


def test_the_pin_is_derived_from_the_command_and_not_written_beside_it() -> None:
    """Article 2 applied to this file: the pin is a claim, so it is read off the code.

    `RESERVED` is the command module's own table of verbs that refuse, and it is
    the same table `commands.main` answers from — so a verb that starts running
    leaves it in the same change, and the row's pin moves with it rather than
    waiting to be remembered.
    """
    assert frozenset(instrument.RESERVED) <= INSTRUMENT_VERBS, sorted(instrument.RESERVED)
    assert INSTRUMENT_VERBS - frozenset(instrument.RESERVED) == RUNNING_VERBS
    # Anti-vacuity: a pin over nothing pins nothing, in either direction.
    assert RUNNING_VERBS
    assert "verify" in RUNNING_VERBS
    assert "verify" not in instrument.RESERVED


def test_the_derivation_moves_the_pin_when_a_reserved_verb_ships(monkeypatch) -> None:
    """The point of deriving it, watched: empty `RESERVED`, and the row goes red.

    The row this repository ships names a refusing half, which is right while
    `apply` refuses. With nothing reserved, the same row is a claim about a verb
    that runs — and the rule says so without this file being edited.
    """
    monkeypatch.setattr(instrument, "RESERVED", {})
    monkeypatch.setattr("test_partition_boundary.RUNNING_VERBS", INSTRUMENT_VERBS)
    with pytest.raises(AssertionError):
        _the_partitions_claim(_state_of("instrument"))
