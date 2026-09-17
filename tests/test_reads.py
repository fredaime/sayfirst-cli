# SPDX-License-Identifier: Apache-2.0
"""Exercise read handling with the real contract and HTTP responses held in memory.

Socket tests own peer verification. These tests catch wrong pagination targets,
result classification and connection cleanup even where sockets cannot bind.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest
from documents import chain_page, problem
from replies import Replies, verified
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.problems import Problem, ProblemCode
from sayfirst_contract.transport.socket_client import SocketClientProblem

from sayfirst_cli import exit_codes
from sayfirst_cli.main import main


@pytest.fixture
def replay(monkeypatch):
    from sayfirst_cli import reads

    def arrange(*responses):
        http = Replies(responses)

        def connect(profile):
            assert profile.scope == "team-ops"
            assert profile.socket_path == "daemon.sock"
            return verified(profile, http)

        monkeypatch.setattr(reads, "connect", connect)
        return http

    return arrange


def run(command, *extra):
    out, err = io.StringIO(), io.StringIO()
    code = main(
        [
            command,
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            "daemon.sock",
            *extra,
        ],
        out=out,
        err=err,
    )
    return code, out.getvalue(), err.getvalue()


def test_explain_preserves_the_record_and_closes_the_connection(replay, record, monkeypatch):
    # A read acts for nobody, even when a privilege tool declares an invoker.
    monkeypatch.setenv("SUDO_USER", "operator")
    monkeypatch.setenv("SUDO_UID", "1001")
    http = replay((200, record))
    code, stdout, stderr = run("explain", "--json")
    assert code == 0
    assert stderr == ""
    assert json.loads(stdout) == {
        "contract_generation": CONTRACT_GENERATION,
        "verification": {"server_uid": 1000, "expected": 1000, "verified": True},
        "result": record,
    }
    assert http.requests == [
        (
            "GET",
            f"/decisions/decision-1?contract_generation={CONTRACT_GENERATION}&scope=team-ops",
            None,
        )
    ]
    assert http.closed


def test_trace_follows_next_from_and_requests_one_hundred_entries(replay, record):
    http = replay((200, record), (200, chain_page(next_from=3)), (200, chain_page(found=True)))
    code, stdout, stderr = run("trace", "--json")
    assert code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"] == {
        **record,
        "chain": {"sequence": 3, "entry_hash": "3" * 64, "grade": "unverified"},
    }
    assert http.requests[1:] == [
        (
            "GET",
            f"/scopes/team-ops/evidence?contract_generation={CONTRACT_GENERATION}"
            "&from_sequence=1&page_size=100",
            None,
        ),
        (
            "GET",
            f"/scopes/team-ops/evidence?contract_generation={CONTRACT_GENERATION}"
            "&from_sequence=3&page_size=100",
            None,
        ),
    ]
    # One reconnect per page: the decision read closed the connection and an
    # evidence read may close its own, so each page is read on a reopened and
    # re-verified one (rule C4). The counter exists to be asserted on.
    assert http.reconnects == 2
    assert http.closed


@pytest.mark.parametrize("next_from", [None, 3])
def test_trace_stops_at_the_end_or_the_requested_bound(replay, record, next_from):
    http = replay((200, record), (200, chain_page(next_from=next_from)))
    code, stdout, stderr = run("trace", "--pages", "1")
    assert code == 0
    assert stderr == ""
    assert stdout.endswith("chain: not found within 1 page(s)\n")
    assert len(http.requests) == 2
    assert http.reconnects == 1
    assert http.closed


def test_trace_default_bound_is_ten_pages(replay, record):
    # Ten pages of a chain, each advancing the read: a page that repeated the
    # sequence it answered would be refused rather than walked ten times.
    http = replay((200, record), *[(200, chain_page(next_from=index)) for index in range(2, 12)])
    code, stdout, stderr = run("trace")
    assert code == 0
    assert stderr == ""
    assert stdout.endswith("chain: not found within 10 page(s)\n")
    assert len(http.requests) == 11
    assert http.reconnects == 10
    assert http.closed


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    ("response", "expected", "problem_code"),
    [
        ((403, problem("peer_not_admitted")), 3, "peer_not_admitted"),
        ((404, problem("decision_not_found")), 3, "decision_not_found"),
        (OSError("connection lost"), 4, "unreachable"),
    ],
)
@pytest.mark.parametrize("stage", ["decision", "page"])
def test_read_failure_keeps_verification_and_never_claims_not_found(
    replay,
    record,
    response,
    expected,
    problem_code,
    stage,
    as_json,
):
    responses = [(200, record), (200, chain_page(next_from=3))] if stage == "page" else []
    http = replay(*responses, response)
    code, stdout, stderr = run("trace", *(["--json"] if as_json else []))
    assert code == expected
    assert stdout == ""
    assert problem_code in stderr
    if as_json:
        envelope = json.loads(stderr)
        assert envelope["verification"]["verified"] is True
        assert envelope["problem"]["code"] == problem_code
        assert "result" not in envelope
    else:
        assert "refused:" in stderr if expected == 3 else "could not ask:" in stderr
    assert http.closed


@pytest.mark.parametrize("command", ["trace", "explain"])
def test_invalid_profile_is_misuse(command):
    code, stdout, stderr = run(command, "--mode", "system")
    assert code == 64
    assert stdout == ""
    assert "names the account" in stderr


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    "problem_code",
    [ProblemCode.GENERATION_UNSUPPORTED, ProblemCode.UNREACHABLE],
    ids=["a code the registry classes as a refusal", "a code it classes as a could-not-ask"],
)
def test_open_failure_is_a_could_not_ask_whatever_the_code(
    monkeypatch,
    problem_code,
    as_json,
):
    """A problem raised while opening the connection is the client's own, so exit 4.

    The registry's class column classifies what the control plane published;
    a problem the client mints for itself — the address could not be opened,
    the profile is pinned to a generation it does not speak — is a could-not-ask
    by construction, because no control plane answered. So the code's column
    does not decide here, and the credentials are unverified because nothing
    was verified.
    """
    expected = 4
    from sayfirst_cli import reads

    def fail(profile):
        raise SocketClientProblem(
            Problem(problem_code, "no connection", False, CONTRACT_GENERATION)
        )

    monkeypatch.setattr(reads, "connect", fail)
    code, stdout, stderr = run("explain", *(["--json"] if as_json else []))
    assert code == expected
    assert stdout == ""
    if as_json:
        assert json.loads(stderr)["verification"] == {
            "server_uid": None,
            "expected": None,
            "verified": False,
        }
    else:
        assert "verified: false" in stderr


def test_shared_finish_also_preserves_untyped_read_documents(replay):
    from sayfirst_contract.client import Answered

    from sayfirst_cli import reads, render

    replay()
    arguments = SimpleNamespace(
        socket="daemon.sock", scope="team-ops", mode="per_user", daemon_user=None, json=True
    )
    out, err = io.StringIO(), io.StringIO()
    connection = reads.open_connection(arguments, err)
    document = chain_page()
    try:
        code = reads.finish(
            Answered(document, CONTRACT_GENERATION),
            arguments,
            connection,
            out,
            err,
            render.write_record,
        )
    finally:
        connection.close()
    assert code == 0
    assert json.loads(out.getvalue())["result"] == document
    assert err.getvalue() == ""


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("command", ["trace", "explain"])
@pytest.mark.parametrize(
    "body", [[1, 2, 3], "x", 5, None], ids=["list", "string", "number", "null"]
)
def test_a_reply_that_is_not_an_object_is_could_not_ask(replay, command, body, as_json):
    """The contract's reader raises `AttributeError` where an object was promised, and
    an answer this client cannot read is « could not ask » — never exit 1, « deny »."""
    http = replay((200, body))
    code, stdout, stderr = run(command, *(["--json"] if as_json else []))
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    if as_json:
        envelope = json.loads(stderr)
        assert envelope["problem"]["code"] == "answer_unreadable"
        assert envelope["problem"]["retryable"] is None  # the registry states none
        assert "result" not in envelope
    else:
        assert "could not ask: answer_unreadable:" in stderr
    assert http.closed


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("command", ["trace", "explain"])
def test_a_record_nested_past_the_bound_is_could_not_ask(replay, record, command, as_json):
    """Rendering the envelope is the step a deep answer overflows, so the bound is
    applied before it. At 9 993 levels the render succeeded and wrote 199 MB; past the
    interpreter's limit it did not survive at all, and exited 1 for a traceback."""
    deep = json.loads("[" * 200 + "]" * 200)
    http = replay((200, {**record, "future_member": deep}), (200, chain_page(found=True)))
    code, stdout, stderr = run(command, *(["--json"] if as_json else []))
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert "nested deeper than" in stderr
    if as_json:
        assert json.loads(stderr)["problem"]["code"] == "answer_unreadable"
    else:
        assert "could not ask: answer_unreadable:" in stderr
    assert http.closed


def test_a_page_nested_past_the_bound_is_could_not_ask(replay, record):
    """A page is bounded before it is walked, not only before it is rendered."""
    deep = json.loads("[" * 200 + "]" * 200)
    http = replay((200, record), (200, {**chain_page(found=True), "future_member": deep}))
    code, stdout, stderr = run("trace", "--json")
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert json.loads(stderr)["problem"]["code"] == "answer_unreadable"
    assert "deeper than" in json.loads(stderr)["problem"]["message"]
    assert http.closed


@pytest.mark.parametrize("command", ["trace", "explain"])
def test_a_reply_the_parser_cannot_read_is_could_not_ask(replay, command):
    """20 000 levels: `json.loads` inside the transport raises `RecursionError`, which
    the transport does not catch and neither command caught until this rule was one."""
    http = replay((200, ("[" * 20000 + "]" * 20000).encode()))
    code, stdout, stderr = run(command, "--json")
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert json.loads(stderr)["problem"]["code"] == "answer_unreadable"
    assert http.closed
