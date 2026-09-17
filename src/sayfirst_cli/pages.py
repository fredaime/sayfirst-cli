# SPDX-License-Identifier: Apache-2.0
"""One evidence page, validated once for every command that walks one.

`trace` and `evidence` both page through scoped evidence, and each carried its
own copy of this. The two copies had already drifted: one refused a `next_from`
that did not advance and the other accepted it, one checked an effect entry's
`decision_id` and the other did not — so one broken daemon reply got two
different answers from two commands of the same commit. The union of both sets
of checks lives here, and both commands now ask the same question of the same
shape.

Only what the commands themselves consume before they claim a match, a position
or an absence is checked. The chain is verified by the contract alone; nothing
here is a second verifier.
"""

from __future__ import annotations

from collections.abc import Mapping

from . import reads


class UnreadablePage(ValueError):
    """An evidence page lacks a member the command that walks it consumes."""


def _checked[T](value: object, expected: type[T], member: str) -> T:
    if not isinstance(value, expected) or (
        expected is int and (isinstance(value, bool) or value < 1)
    ):
        raise UnreadablePage(f"evidence page member {member} is missing or invalid")
    return value


def members(
    page: Mapping[str, object], from_sequence: int
) -> tuple[list[Mapping[str, object]], Mapping[str, object], int | None]:
    """The page's entries, its served verdict and its continuation.

    `next_from` has to be there and it has to advance. A page that answers a
    read from sequence 5 with `next_from: 5` is not a continuation, and walking
    it again until a page budget runs out ends in « not found » — an absence
    stated as a fact the read never established (article 2).
    """
    if reads.too_deep(page, reads.PAGE_DEPTH_LIMIT):
        # One page, bounded two levels shallower than a whole answer, because a
        # page is carried inside one: `reads.PAGE_DEPTH_LIMIT` says why, and the
        # subtraction lives there so this file cannot hold a second copy of it.
        raise UnreadablePage(
            f"evidence page nests deeper than {reads.PAGE_DEPTH_LIMIT} levels; "
            "not a page this client reads"
        )
    entries = _checked(page.get("entries"), list, "entries")
    for index, value in enumerate(entries):
        prefix = f"entries[{index}]"
        entry = _checked(value, Mapping, prefix)
        _checked(entry.get("sequence"), int, f"{prefix}.sequence")
        for name in ("kind", "connection_id", "entry_hash"):
            _checked(entry.get(name), str, f"{prefix}.{name}")
        body = _checked(entry.get("body"), Mapping, f"{prefix}.body")
        if entry["kind"] == "effect":
            # The member `trace` reads to decide whether an entry is the one it
            # was asked about: a page that lacks it cannot answer the question.
            _checked(body.get("decision_id"), str, f"{prefix}.body.decision_id")
    served = _checked(page.get("verification"), Mapping, "verification")
    for name, fields in (
        ("grades", (("connection_id", str), ("grade", str))),
        ("declared_gaps", (("sequence", int), ("reason", str), ("count", int))),
    ):
        items = _checked(served.get(name), list, f"verification.{name}")
        for index, value in enumerate(items):
            prefix = f"verification.{name}[{index}]"
            item = _checked(value, Mapping, prefix)
            for field, expected in fields:
                _checked(item.get(field), expected, f"{prefix}.{field}")
    _checked(served.get("condition"), str, "verification.condition")
    if served.get("sequence") is not None:
        _checked(served["sequence"], int, "verification.sequence")
    if "next_from" not in page:
        raise UnreadablePage("evidence page member next_from is missing")
    next_from = page["next_from"]
    if next_from is not None:
        _checked(next_from, int, "next_from")
        if next_from <= from_sequence:
            raise UnreadablePage("evidence page member next_from does not advance the read")
    return entries, served, next_from
