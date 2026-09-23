# SPDX-License-Identifier: Apache-2.0
"""Evidence pagination and verification over the real transport with in-memory HTTP replies."""

from __future__ import annotations

import io
import json
import os

import pytest
from documents import arguments, entry_lines, evidence_page, problem
from replies import Replies, verified
from sayfirst_contract.evidence import verify_chain
from sayfirst_contract.generation import CONTRACT_GENERATION

from sayfirst_cli import exit_codes, reads
from sayfirst_cli.main import main


def run(command, *argv, out=None):
    out, err = out if out is not None else io.StringIO(), io.StringIO()
    code = main(["evidence", command, *argv], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def replay(monkeypatch):
    def arrange(*responses):
        http = Replies(responses)

        def connect(profile, **_):
            assert profile.scope == "local"
            assert profile.socket_path == os.path.abspath("daemon.sock")
            return verified(profile, http)

        monkeypatch.setattr(reads, "connect", connect)
        return http

    return arrange


@pytest.mark.parametrize("all_pages", [False, True])
@pytest.mark.parametrize("page_size", [None, 2, 100])
def test_history_uses_the_requested_page_size_and_continuation(
    replay, entries, all_pages, page_size
):
    pages = [evidence_page(entries[:2], next_from=3), evidence_page(entries[2:], from_sequence=3)]
    http = replay(*((200, document) for document in pages))
    code, stdout, stderr = run(
        "history",
        *arguments(
            "daemon.sock",
            "--json",
            *(["--all"] if all_pages else []),
            *(["--page-size", str(page_size)] if page_size is not None else []),
        ),
    )
    assert code == 0
    assert json.loads(stdout)["result"] == {"pages": pages if all_pages else pages[:1]}
    assert http.requests == [
        (
            "GET",
            f"/scopes/local/evidence?contract_generation={CONTRACT_GENERATION}"
            f"&from_sequence={start}&page_size={page_size or 100}",
            None,
        )
        for start in ([1, 3] if all_pages else [1])
    ]
    # One reconnect per page after the first: an evidence read may close its
    # HTTP connection and the transport never re-dials one (rule C4).
    assert http.reconnects == (1 if all_pages else 0)
    assert http.closed
    assert stderr == ""


def test_history_writes_each_page_before_reading_the_next(replay, entries):
    out = io.StringIO()

    def responses():
        yield 200, evidence_page(entries[:2], next_from=3)
        assert out.getvalue().splitlines() == entry_lines(entries[:2])
        yield 200, evidence_page(entries[2:], from_sequence=3)

    http = replay()
    http.responses = iter(responses())
    code, stdout, stderr = run("history", *arguments("daemon.sock", "--all"), out=out)
    assert code == 0
    assert stdout.splitlines() == [*entry_lines(entries), "next_from: none"]
    assert http.closed
    assert stderr == ""


@pytest.mark.parametrize("to_sequence", [None, 2, 3, 4])
def test_audit_checks_collected_entries_and_stops_at_the_requested_bound(
    replay, entries, to_sequence
):
    pages = [
        evidence_page(entries[:2], next_from=3),
        evidence_page(entries[2:], from_sequence=3, verified_entries=entries),
    ]
    http = replay(*((200, document) for document in pages))
    code, stdout, stderr = run(
        "audit",
        *arguments(
            "daemon.sock",
            "--json",
            *(["--to", str(to_sequence)] if to_sequence is not None else []),
        ),
    )
    local = verify_chain(
        entries[:2] if to_sequence == 2 else entries,
        scope="local",
        from_sequence=1,
        to_sequence=to_sequence,
    )
    assert json.loads(stdout)["result"] == {
        "served": pages[0 if to_sequence == 2 else 1]["verification"],
        "local_check": local.to_document(),
        "pages": 1 if to_sequence == 2 else 2,
    }
    assert code == (exit_codes.EXIT_CHECK_FAILED if to_sequence == 4 else 0)
    assert len(http.requests) == (1 if to_sequence == 2 else 2)
    assert http.closed
    assert stderr == ""


@pytest.mark.parametrize("next_from", [None, 2, 4])
def test_audit_ignores_corruption_after_the_bound_within_a_page(replay, entries, next_from):
    document = evidence_page(entries, next_from=next_from)
    document["entries"][2]["body"]["outcome"] = "allow"
    http = replay((200, document), (503, problem("evidence_store_unavailable")))
    code, stdout, stderr = run("audit", *arguments("daemon.sock", "--to", "2"))
    assert code == 0
    assert "verification: intact\nlocal_check: intact\n" in stdout
    assert "local_check.sequence:" not in stdout
    assert "finding:" not in stdout
    assert len(http.requests) == 1
    assert http.closed
    assert stderr == ""


def test_audit_passes_from_sequence_to_the_transport_and_verifier(replay, entries):
    document = evidence_page(entries[1:], from_sequence=2)
    document["verification"] = verify_chain(
        entries[1:], scope="local", from_sequence=2
    ).to_document()
    http = replay((200, document))
    code, stdout, stderr = run("audit", *arguments("daemon.sock", "--from", "2", "--json"))
    assert code == 0
    assert json.loads(stdout)["result"] == {
        "served": document["verification"],
        "local_check": document["verification"],
        "pages": 1,
    }
    assert "&from_sequence=2&page_size=100" in http.requests[0][1]
    assert http.closed
    assert stderr == ""


@pytest.mark.parametrize("as_json", [False, True])
def test_audit_detects_tampering_with_the_served_verdict_unchanged(replay, entries, as_json):
    document = evidence_page(entries)
    document["entries"][1]["body"]["grade"] = "evidence"
    http = replay((200, document))
    code, stdout, stderr = run("audit", *arguments("daemon.sock", *(["--json"] if as_json else [])))
    assert code == exit_codes.EXIT_CHECK_FAILED
    if as_json:
        result = json.loads(stdout)["result"]
        assert result["served"] == document["verification"]
        assert result["pages"] == 1
        assert (
            result["local_check"]
            == verify_chain(document["entries"], scope="local", from_sequence=1).to_document()
        )
    else:
        assert "verification: intact\nlocal_check: broken_at\nlocal_check.sequence: 2\n" in stdout
        assert "local_check.expected:" in stdout
        assert "local_check.found:" in stdout
        assert "finding: the plane says intact, the local check says broken_at\n" in stdout
    assert http.closed
    assert stderr == ""


@pytest.mark.parametrize("served", ["broken_at", "gap_at", "unverifiable"])
def test_served_disagreement_is_a_finding_with_exit_six(replay, entries, served):
    document = evidence_page(entries)
    document["verification"].update(condition=served, sequence=2)
    replay((200, document))
    code, stdout, stderr = run("audit", *arguments("daemon.sock"))
    assert code == exit_codes.EXIT_CHECK_FAILED
    assert stdout.startswith(
        f"verification: {served}\nverification.sequence: 2\nlocal_check: intact\n"
    )
    assert f"finding: the plane says {served}, the local check says intact\n" in stdout
    assert stderr == ""


def test_inconclusive_local_check_stays_exit_seven_despite_disagreement(replay):
    document = evidence_page([])
    document["verification"]["condition"] = "intact"
    replay((200, document))
    code, stdout, stderr = run("audit", *arguments("daemon.sock"))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert "verification: intact\nlocal_check: unverifiable\n" in stdout
    assert "finding: the plane says intact, the local check says unverifiable\n" in stdout
    assert stderr == ""


@pytest.mark.parametrize("command", ["history", "audit"])
@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    ("failure", "expected", "problem_code"),
    [
        ((403, problem("peer_not_admitted")), 3, "peer_not_admitted"),
        ((503, problem("evidence_store_unavailable")), 4, "evidence_store_unavailable"),
        (OSError("connection lost"), 4, "unreachable"),
    ],
)
def test_interrupted_walk_does_not_conclude(
    replay, entries, command, as_json, failure, expected, problem_code
):
    http = replay((200, evidence_page(entries[:2], next_from=3)), failure)
    code, stdout, stderr = run(
        command,
        *arguments(
            "daemon.sock",
            *(["--all"] if command == "history" else []),
            *(["--json"] if as_json else []),
        ),
    )
    assert code == expected
    assert "local_check" not in stdout
    assert "from_sequence 3" in stderr
    assert problem_code in stderr
    if as_json:
        envelope = json.loads(stderr)
        assert envelope["problem"]["code"] == problem_code
        assert envelope["verification"]["verified"] is True
    elif command == "history":
        assert stdout.splitlines() == entry_lines(entries[:2])
    else:
        assert stdout == ""
    assert http.closed


@pytest.mark.parametrize("command", ["history", "audit"])
@pytest.mark.parametrize(
    ("member", "value"),
    [
        ("entries", None),
        ("entries", [{}]),
        ("verification", {}),
        ("next_from", ...),
        ("next_from", True),
        ("next_from", "3"),
        ("next_from", 1),
    ],
)
def test_unreadable_pages_are_problems_never_tracebacks(replay, entries, command, member, value):
    document = evidence_page(entries)
    if value is ...:
        del document[member]
    else:
        document[member] = value
    http = replay((200, document))
    code, stdout, stderr = run(command, *arguments("daemon.sock", "--json"))
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert json.loads(stderr)["problem"]["code"] == "answer_unreadable"
    assert member in json.loads(stderr)["problem"]["message"]
    assert http.closed


@pytest.mark.parametrize("command", ["history", "audit"])
def test_invalid_sequence_range_is_a_usage_error(command):
    with pytest.raises(SystemExit) as failure:
        run(command, *arguments("daemon.sock", "--from", "0"))
    assert failure.value.code == 2


def test_reversed_audit_range_is_a_usage_error():
    with pytest.raises(SystemExit) as failure:
        run("audit", *arguments("daemon.sock", "--from", "3", "--to", "2"))
    assert failure.value.code == 2


def test_a_delegation_that_is_not_a_chain_is_a_local_check_and_never_a_non_answer(replay, entries):
    """A principal whose delegation is not a chain: the answer arrived, the check did not.

    « The plane could not be asked » and « the chain could not be judged » are
    different facts about different things, and this is the second: the page was
    served, read and held. It answers 7 with the verdict, and the connection is
    still closed on the way out.
    """
    document = evidence_page(entries)
    document["entries"][0]["principal"]["via"] = [None]
    http = replay((200, document))
    code, stdout, stderr = run("audit", *arguments("daemon.sock", "--json"))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert code != exit_codes.EXIT_COULD_NOT_ASK
    assert stderr == ""
    assert json.loads(stdout)["result"]["local_check"]["condition"] == "unverifiable"
    assert http.closed


def test_an_instant_outside_the_calendar_is_rendered_with_what_could_not_be_judged(replay, entries):
    """The same fact through the other shape, with the whole verdict in the envelope.

    The sequence is what a reader acts on, so it is asserted rather than assumed:
    an `unverifiable` carrying no position would be « something is wrong
    somewhere », which is an absence stated as a fact (article 2).
    """
    document = evidence_page(entries)
    document["entries"][0]["recorded_at"] = "0001-01-01T00:00:00+01:00"
    http = replay((200, document))
    code, stdout, stderr = run("audit", *arguments("daemon.sock", "--json"))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stderr == ""
    envelope = json.loads(stdout)
    assert "problem" not in envelope
    assert envelope["result"]["local_check"]["condition"] == "unverifiable"
    assert envelope["result"]["local_check"]["sequence"] == 1
    assert envelope["verification"] == {"server_uid": 1000, "expected": 1000, "verified": True}
    assert http.closed
