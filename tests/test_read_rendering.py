# SPDX-License-Identifier: Apache-2.0
"""Read rendering preserves the record and keeps checking distinct from asking."""

import io

import pytest

from sayfirst_cli import exit_codes, render


def test_local_check_codes_are_distinct_from_outcomes_and_read_failures() -> None:
    """The name is the claim, so the body makes it: a local check is neither an
    outcome the plane gave nor a failure to reach it, and shares no code with one."""
    assert exit_codes.EXIT_CHECK_FAILED == 6
    assert exit_codes.EXIT_COULD_NOT_CHECK == 7
    assert exit_codes.CODES["check_failed"] == 6
    assert exit_codes.CODES["could_not_check"] == 7
    local_checks = {"check_failed", "could_not_check"}
    others = {code for name, code in exit_codes.CODES.items() if name not in local_checks}
    assert exit_codes.EXIT_CHECK_FAILED not in others
    assert exit_codes.EXIT_COULD_NOT_CHECK not in others
    # Anti-vacuity: a CODES that held only the two would satisfy the lines above.
    assert len(others) == len(exit_codes.CODES) - 2


def test_record_members_are_ordered_and_absence_is_stated() -> None:
    document = {
        "z_extra": None,
        "approval_ref": None,
        "grant_id": None,
        "correlation": None,
        "decided_at": "instant",
        "policy_version": "policy-1",
        "rule_id": "deny-one",
        "reason": "policy_denies",
        "outcome": "deny",
        "capability": "example.effect",
        "scope": "team-ops",
        "decision_ref": "decision-1",
        "a_extra": False,
    }
    stream = io.StringIO()
    render.write_record(document, stream)
    assert stream.getvalue().splitlines() == [
        "decision_ref: decision-1",
        "scope: team-ops",
        "capability: example.effect",
        "outcome: deny",
        "reason: policy_denies",
        "rule_id: deny-one",
        "policy_version: policy-1",
        "decided_at: instant",
        "correlation: not stated",
        "grant_id: not stated",
        "approval_ref: not stated",
        "a_extra: False",
        "z_extra: not stated",
    ]


@pytest.mark.parametrize(
    ("position", "expected"),
    [
        (
            {"sequence": 3, "entry_hash": "abc", "grade": "unknown"},
            "chain: sequence 3, entry_hash abc, grade unknown\n",
        ),
        ({"found": False, "pages": 1}, "chain: not found within 1 page(s)\n"),
    ],
)
def test_chain_position_is_rendered_as_supplied(position, expected: str) -> None:
    stream = io.StringIO()
    render.write_chain_position(position, stream)
    assert stream.getvalue() == expected
