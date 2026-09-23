# SPDX-License-Identifier: Apache-2.0
"""The daemon documents these tests hand to the client, each spelled once.

Two different page shapes were defined under the name `page` in two sibling test
files and imported crosswise, so `page(...)` meant one thing in the trace tests
and another in the evidence tests. They are different documents — one is built
from the contract's schema examples, the other from the published manifest
vectors and the contract's own verifier — so here they are named as what they
are, and nothing imports a fixture out of a neighbouring test module.
"""

from __future__ import annotations

import os
import pwd
from collections.abc import Mapping
from copy import deepcopy

from sayfirst_contract.artifacts import load_json
from sayfirst_contract.decisions import Decision, Outcome, Reason
from sayfirst_contract.evidence import verify_chain
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.golden import schema_examples


def approval_record(**changes: object) -> dict[str, object]:
    """The published `approval-result`, of this generation, with the named changes."""
    document = {
        **schema_examples()["approval-result"],
        "contract_generation": CONTRACT_GENERATION,
        "approval_ref": "approval-1",
        "decision_ref": "decision-1",
        "scope": "team-ops",
    }
    document.update(changes)
    return document


def decision_record() -> dict[str, object]:
    """One recorded decision, with members this generation does not define."""
    return Decision(
        decision_ref="decision-1",
        scope="team-ops",
        capability="example.effect",
        outcome=Outcome.DENY,
        reason=Reason.POLICY_DENIES,
        policy_version="policy-1",
        approval_ref=None,
        decided_at="2026-09-04T00:00:00+00:00",
        correlation=None,
        contract_generation=CONTRACT_GENERATION,
        extra={
            "principal": {"kind": "process", "uid": 1000, "name": "build"},
            "arguments_digest": "sha256:" + "0" * 64,
            "rule_id": "deny-one",
            "grant_id": None,
            "authority": "authoritative",
            "future_member": {"preserve": True},
        },
    ).to_document()


def chain_page(*, found: bool = False, next_from: int | None = None) -> dict[str, object]:
    """A page of the chain `trace` walks, built from the contract's examples."""
    examples = schema_examples()
    entry = {
        **examples["evidence-entry"],
        "scope": "team-ops",
        "sequence": 3,
        "entry_hash": "3" * 64,
        "previous_hash": "2" * 64,
        "body": {**examples["evidence-entry"]["body"], "outcome": "deny"},
    }
    return {
        **examples["evidence-page-result"],
        "contract_version": str(CONTRACT_GENERATION),
        "scope": "team-ops",
        "from_sequence": 3 if found else 1,
        "to_sequence": 3 if found else None,
        "entries": [entry] if found else [],
        "verification": {
            **examples["evidence-verdict"],
            "scope": "team-ops",
            "from_sequence": 3 if found else 1,
            "to_sequence": 3 if found else None,
            "up_to": 3 if found else None,
            "covers_an_entry": found,
            "grades": [{"connection_id": "connection-1", "grade": "unverified"}],
        },
        "next_from": next_from,
    }


def vector_entries() -> list[dict[str, object]]:
    """The entries of the published `v1_intact_range` bundle: a real chain."""
    vectors = load_json("domain", "evidence-export-manifest-vectors.json")["vectors"]
    return next(
        vector["bundle"]["entries"] for vector in vectors if vector["name"] == "v1_intact_range"
    )


def evidence_page(
    entries, *, from_sequence=1, next_from=None, verified_entries=None
) -> dict[str, object]:
    """A page of scoped evidence, its verdict computed by the contract's verifier."""
    return {
        "contract_version": str(CONTRACT_GENERATION),
        "scope": "local",
        "from_sequence": from_sequence,
        "to_sequence": entries[-1]["sequence"] if entries else None,
        "entries": deepcopy(entries),
        "verification": verify_chain(
            entries if verified_entries is None else verified_entries,
            scope="local",
            from_sequence=1,
        ).to_document(),
        "next_from": next_from,
    }


def _how_deep(value: object) -> int:
    """How many levels a document nests, counted the way `reads.too_deep` counts."""
    deepest = 0
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        deepest = max(deepest, depth)
        if isinstance(item, Mapping):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return deepest


def chain_page_nested(*, levels: int, next_from: int | None = None) -> dict[str, object]:
    """A real page, padded so the ANSWER a paging read composes nests `levels` deep.

    `levels` is measured on `{"pages": [page]}` and not on the page, because
    that is the document `evidence history` hands to the renderer: a page sits
    three levels down in it, so its own deepest member lands two levels deeper
    than it measures alone. Asking for the answer's depth rather than the page's
    is what lets a test say « exactly at the bound » and mean the bound that
    decides whether anything is written.

    The chain is a real one, so a page at the bound still renders as an answer
    and `evidence audit` still concludes `intact` on it: a padded page that
    could not be verified would prove the refusal and nothing about the render.
    """
    page = evidence_page(vector_entries(), next_from=next_from)
    nested: object = None
    for _ in range(max(levels - 4, 0)):
        nested = {"nested": nested}
    page["nested"] = nested
    assert _how_deep({"pages": [page]}) == levels, "the padding does not reach the asked-for depth"
    return page


def entry_lines(entries) -> list[str]:
    """The lines `evidence history` writes for those entries."""
    return [
        f"{entry['sequence']} {entry['kind']} {entry['connection_id']} {entry['entry_hash']}"
        for entry in entries
    ]


def arguments(address, *extra) -> list[str]:
    """The scope, socket and `--from` every online evidence read requires."""
    return ["--scope", "local", "--socket", str(address), "--from", "1", *extra]


def problem(code: str) -> dict[str, object]:
    """The published problem document a daemon returns with a non-200 status."""
    return {
        "contract_generation": CONTRACT_GENERATION,
        "code": code,
        "message": "the requested read could not be answered",
        "retryable": False,
    }


def no_evidence_page(*, from_sequence: int = 1) -> dict[str, object]:
    """A page of a scope whose chain holds nothing yet.

    The shape the daemon serves for an empty range, taken from the contract's
    own example: entries absent and a verdict that says `unverifiable` rather
    than `intact`, because a range covering no entry is not a sound one
    (article 2).
    """
    return {
        **schema_examples()["evidence-page-result"],
        "contract_version": str(CONTRACT_GENERATION),
        "from_sequence": from_sequence,
        "entries": [],
        "next_from": None,
    }


#: The principal a record carries when it was NOT recorded for the execution
#: under proof. A name no account on any host is spelled with, so that « this
#: record is somebody else's » is a property of the fixture and never an
#: accident of whoever runs the suite.
ANOTHER_ACCOUNT: dict[str, object] = {"kind": "user", "id": "another-account!", "via": []}

#: The connection a record carries when another execution asked for it. The
#: daemon gives one connection one identifier, so two executions never share it.
ANOTHER_EXECUTION = "another-execution"


def this_executions_principal() -> dict[str, object]:
    """The principal the daemon records for a connection from THIS process.

    Article 6: identity is the operating system's, and the daemon builds the
    principal from the peer credential of the connection — the account this
    process runs as. A fixture claiming to be a record of the run under proof
    has to carry that identity, because that is the one thing about a record
    which says the run under proof is the run it was recorded for.
    """
    try:
        name: object = pwd.getpwuid(os.geteuid()).pw_name
    except KeyError:  # pragma: no cover - a uid with no account
        name = str(os.geteuid())
    return {"kind": "user", "id": name, "via": []}


def recorded_effect_page(
    capability: str,
    *,
    sequence: int = 1,
    outcome: str = "allow",
    from_sequence: int = 1,
    next_from: int | None = None,
    count: int = 1,
    principal: Mapping[str, object] | None = None,
    connection_id: str = "connection-1",
    condition: str | None = None,
) -> dict[str, object]:
    """A page holding recorded effects of the execution under proof.

    **What this fixture carries, and why it is not two members.** It varied
    exactly the two members the matcher consumed — the body's capability and
    its outcome — and so it could not see the defect that the matcher consumed
    only those two: a record of another execution, another principal and
    another call satisfied every success fixture in this repository. The
    invariant that replaces « vary what the matcher reads » is « a success
    fixture carries the identity of the execution under proof »: by default the
    principal this process would be recorded as, and one connection identifier.
    `ANOTHER_ACCOUNT` and `ANOTHER_EXECUTION` are what a record of somebody
    else looks like, and a fixture built from either is not a success fixture.

    `condition` overrides what the served verification says about the range the
    record sits in. The default is the contract's own example, which reports the
    chain intact; a page reporting anything else is evidence this client may not
    take a record from, and saying so is this argument's whole purpose.

    `count` puts several records of the one capability on the page, from
    `sequence` upwards. A test that has to prove the verifier counted the
    program's events and nothing else needs more records than the program has
    effects: with one record, « one event was judged » and « the pool ran dry »
    look the same.
    """
    examples = schema_examples()
    entries = [
        {
            **examples["evidence-entry"],
            "sequence": sequence + offset,
            "entry_hash": f"{sequence + offset:064d}",
            "connection_id": connection_id,
            "principal": dict(this_executions_principal() if principal is None else principal),
            "body": {
                **examples["evidence-entry"]["body"],
                "capability": capability,
                "outcome": outcome,
            },
        }
        for offset in range(count)
    ]
    last = sequence + count - 1
    verification = {
        **examples["evidence-verdict"],
        "from_sequence": from_sequence,
        "to_sequence": last,
        "up_to": last,
    }
    if condition is not None:
        verification["condition"] = condition
        verification["sequence"] = sequence
    return {
        **examples["evidence-page-result"],
        "contract_version": str(CONTRACT_GENERATION),
        "from_sequence": from_sequence,
        "entries": entries,
        "to_sequence": last,
        "verification": verification,
        "next_from": next_from,
    }


def another_executions_effect_page(capability: str, **changes: object) -> dict[str, object]:
    """The same page, recorded for another principal on another connection.

    Nothing about it says it is this run's, which is the whole of it: a
    verifier that reports `governed` from this page has proven that a decision
    exists somewhere, never that one preceded the effect it watched.
    """
    return recorded_effect_page(
        capability,
        principal=ANOTHER_ACCOUNT,
        connection_id=ANOTHER_EXECUTION,
        **changes,  # type: ignore[arg-type]
    )


def foreign_generation_page(*, from_sequence: int = 1) -> dict[str, object]:
    """A page a daemon of a generation this client does not speak would serve.

    The transport refuses it as `generation_unsupported` (article 13: the
    generation is echoed on every answer and compared to the one the connection
    was opened on), so it is a read that arrives and is not an answer — which
    is the one thing a verifier must not read as an absence of records.
    """
    return {
        **no_evidence_page(from_sequence=from_sequence),
        "contract_version": str(CONTRACT_GENERATION + 1),
    }
