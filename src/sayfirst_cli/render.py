# SPDX-License-Identifier: Apache-2.0
"""How an answer reaches a person, and what this client is not allowed to add.

Article 1: a client explains and invokes control semantics; it never derives an
answer the control plane did not give. So every member of the envelope below is
either something the control plane said, something the operating system said, or
something this process did — and each is labelled as which. Nothing is computed
from an answer and presented beside it as though it were part of it.

Article 2: an absence is never rendered as a negative fact, a zero or a healthy
state. Where the answer carries no policy version, no approval reference and no
reason this generation knows, the rendering says so in words rather than leaving
a blank the reader completes with a guess.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TextIO

#: What is written where the control plane said nothing. It is a sentence and
#: not an empty string, because a blank field reads as a value (article 2).
NOT_STATED = "not stated"


def verification_document(
    server_uid: int | None, expected_uid: int | None, verified: bool
) -> dict[str, object]:
    """What this process verified about the far end before it wrote a byte.

    This is the one part of the envelope the control plane did not say: the
    client read the server's peer credential and compared it (article 6). It is
    kept in a member of its own so that no reader can mistake it for something
    the daemon claimed about itself.
    """
    return {"server_uid": server_uid, "expected": expected_uid, "verified": verified}


def envelope(
    contract_generation: int,
    verification: Mapping[str, object],
    *,
    result: Mapping[str, object] | None = None,
    problem: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """The machine-readable form: the answer, or the problem, and never both."""
    document: dict[str, object] = {
        "contract_generation": contract_generation,
        "verification": dict(verification),
    }
    if result is not None:
        document["result"] = dict(result)
    if problem is not None:
        document["problem"] = dict(problem)
    return document


def write_json(document: Mapping[str, object], stream: TextIO) -> None:
    """The whole envelope, stable under sorting so a diff of two runs is readable."""
    stream.write(json.dumps(document, indent=2, sort_keys=True))
    stream.write("\n")


def _stated(value: object) -> str:
    """A member as a person reads it, with absence said rather than shown."""
    return NOT_STATED if value is None else str(value)


def write_decision(document: Mapping[str, object], stream: TextIO) -> None:
    """A decision, in the words the control plane used for it.

    The outcome is written as the control plane spelled it. This client holds no
    table from `allow` to "approved" or from `deny` to "blocked": a second
    vocabulary for the same three outcomes is a second control plane, without
    the evidence (articles 1 and 4).
    """
    stream.write(f"outcome: {document['outcome']}\n")
    stream.write(f"reason: {_stated(document.get('reason'))}\n")
    stream.write(f"capability: {document['capability']} in scope {document['scope']}\n")
    stream.write(f"decision: {document['decision_ref']} at {document['decided_at']}\n")
    stream.write(f"policy version: {_stated(document.get('policy_version'))}\n")
    if document.get("approval_ref") is not None:
        stream.write(f"approval: {document['approval_ref']}\n")


def write_verification(document: Mapping[str, object], stream: TextIO) -> None:
    """What was verified about the far end, in the words `sayfirstd whoami` uses.

    One difference, on purpose: an absent value is said here (`not stated`),
    where that command prints Python's `None`.
    """
    stream.write(
        f"verified: {str(document['verified']).lower()} "
        f"(server_uid {_stated(document['server_uid'])}, "
        f"expected {_stated(document['expected'])})\n"
    )


def write_record(document: Mapping[str, object], stream: TextIO) -> None:
    """Every supplied record member, with its reason and rule on their own lines."""
    order = (
        "decision_ref",
        "scope",
        "capability",
        "outcome",
        "reason",
        "rule_id",
        "policy_version",
        "decided_at",
        "correlation",
        "grant_id",
        "approval_ref",
    )
    for key in (*order, *sorted(document.keys() - set(order))):
        if key in document:
            stream.write(f"{key}: {_stated(document[key])}\n")


def write_chain_position(position: Mapping[str, object], stream: TextIO) -> None:
    """The position and grade the plane supplied, or the bound actually read."""
    if position.get("found") is False:
        stream.write(f"chain: not found within {position['pages']} page(s)\n")
    else:
        stream.write(
            f"chain: sequence {position['sequence']}, entry_hash {position['entry_hash']}, "
            f"grade {position['grade']}\n"
        )


def write_problem(document: Mapping[str, object], stream: TextIO, *, could_not_ask: bool) -> None:
    """A refusal or an unanswerable question, each said as what it is.

    Article 1: "could not ask" is never written as "denied" or as "allowed", and
    article 2 adds that it is not a negative fact either. The line therefore
    names which of the two happened before it names the code, because the code
    alone does not tell a reader whether an answer exists somewhere.
    """
    kind = "could not ask" if could_not_ask else "refused"
    stream.write(f"{kind}: {document['code']}: {document['message']}\n")
    retryable = document.get("retryable")
    stream.write(f"retryable: {NOT_STATED if retryable is None else str(retryable).lower()}\n")
