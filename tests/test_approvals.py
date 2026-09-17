# SPDX-License-Identifier: Apache-2.0
"""`sayfirst approvals show|approve|reject`: one person, one wait, one record.

Peer verification and the wire behind a daemon that closes after its answer
are held over sockets, exactly as `test_reads.py` holds them for `trace` and
`explain`. Everything else — which target was asked, what a POST carried, how
many times the connection was reconnected — is held with `Replies`, because a
socket cannot answer any of those questions cheaply.
"""

from __future__ import annotations

import io
import json

import pytest
from canned_daemon import answering_by_path
from documents import approval_record, problem
from replies import Replies, verified
from sayfirst_contract.generation import CONTRACT_GENERATION

from sayfirst_cli import exit_codes
from sayfirst_cli.main import main


def run(command: str, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(["approvals", command, *argv], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def arguments(*extra: str) -> list[str]:
    return ["--scope", "team-ops", "--socket", "daemon.sock", "--approval", "approval-1", *extra]


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


# -- show ----------------------------------------------------------------


def test_show_renders_a_pending_wait(replay):
    http = replay((200, approval_record(state="pending")))
    code, stdout, stderr = run("show", *arguments())
    assert code == 0
    assert stderr == ""
    assert "approval: approval-1\n" in stdout
    assert "decision: decision-1\n" in stdout
    assert "state: pending\n" in stdout
    assert "resolved_at: not stated\n" in stdout
    assert "reason: not stated\n" in stdout
    assert http.requests == [
        (
            "GET",
            f"/approvals/approval-1?contract_generation={CONTRACT_GENERATION}&scope=team-ops",
            None,
        )
    ]
    # `read_approval` is left open by the daemon (the transport's own
    # docstring), and `show` reads exactly once, so nothing here ever calls
    # `reconnect()` — the connection is not re-dialled.
    assert http.reconnects == 0
    assert http.closed


def test_show_renders_an_already_approved_wait(replay):
    replay(
        (
            200,
            approval_record(
                state="approved",
                resolved_at="2026-09-16T00:00:30+00:00",
                resolution_reason="looked fine",
            ),
        )
    )
    code, stdout, stderr = run("show", *arguments())
    assert code == 0
    assert stderr == ""
    assert "state: approved\n" in stdout
    assert "resolved_at: 2026-09-16T00:00:30+00:00\n" in stdout
    assert "reason: looked fine\n" in stdout


def test_show_json_preserves_the_whole_record(replay):
    document = approval_record(state="pending")
    replay((200, document))
    code, stdout, stderr = run("show", *arguments("--json"))
    assert code == 0
    envelope = json.loads(stdout)
    assert envelope["result"] == document
    assert envelope["contract_generation"] == CONTRACT_GENERATION
    assert stderr == ""


def test_show_survives_a_daemon_that_closes_after_the_answer(tmp_path):
    """The real daemon leaves this connection open; this proves `show` needs no
    reconnect even against one that does not, because it reads only once."""
    routes = {"/approvals/": (200, approval_record(state="pending"))}
    with answering_by_path(tmp_path / "d.sock", routes, close_after_each=True) as address:
        code, stdout, stderr = run(
            "show", "--scope", "team-ops", "--approval", "approval-1", "--socket", str(address)
        )
    assert code == 0, (stdout, stderr)
    assert "state: pending\n" in stdout
    assert stderr == ""


# -- approve / reject ------------------------------------------------------


@pytest.mark.parametrize(("command", "state"), [("approve", "approved"), ("reject", "rejected")])
def test_resolve_renders_the_record_the_daemon_returns(replay, command, state):
    document = approval_record(
        state=state, resolved_at="2026-09-16T00:00:30+00:00", resolution_reason="the walk approves"
    )
    http = replay((200, document))
    code, stdout, stderr = run(command, *arguments("--reason", "the walk approves"))
    assert code == 0
    assert stderr == ""
    assert f"state: {state}\n" in stdout
    assert "reason: the walk approves\n" in stdout
    assert http.reconnects == 0
    assert http.closed


@pytest.mark.parametrize(("command", "resolution"), [("approve", "approve"), ("reject", "reject")])
def test_reason_travels_on_the_wire(replay, command, resolution):
    http = replay((200, approval_record(state="approved")))
    run(command, *arguments("--reason", "the walk approves"))
    method, target, body = http.requests[0]
    assert method == "POST"
    assert target == "/approvals/approval-1/resolution"
    assert json.loads(body) == {
        "contract_generation": CONTRACT_GENERATION,
        "scope": "team-ops",
        "approval_ref": "approval-1",
        "resolution": resolution,
        "reason": "the walk approves",
    }


def test_omitted_reason_is_not_put_on_the_wire(replay):
    http = replay((200, approval_record(state="approved")))
    run("approve", *arguments())
    _, _, body = http.requests[0]
    assert "reason" not in json.loads(body)


# -- the classifications the registry publishes ----------------------------


def test_an_unknown_approval_is_a_refusal_by_the_registrys_code(replay):
    """The daemon looked in this scope and keeps no wait with that reference.

    An answer about the question, not an absence of one: the contract's
    registry classes `approval_unknown` a refusal, and this command renders
    what the transport gave it rather than deciding for itself.
    """
    replay((404, problem("approval_unknown")))
    code, stdout, stderr = run("show", *arguments())
    assert code == exit_codes.EXIT_REFUSED
    assert stdout == ""
    assert "refused: approval_unknown" in stderr
    assert "could not ask:" not in stderr


def test_a_resolved_approval_is_a_refusal_by_the_registrys_code(replay):
    """A wait that is already over is not ended twice, and the daemon says so.

    The act reached the daemon and the daemon rejected it, which is what the
    registry's class column publishes for `approval_resolved`; a resolution
    creates a record and never edits one. This command never special-cases a
    code the transport gave it, so the refusal is exit 3.
    """
    replay((409, problem("approval_resolved")))
    code, stdout, stderr = run("approve", *arguments())
    assert code == exit_codes.EXIT_REFUSED
    assert stdout == ""
    assert "refused: approval_resolved" in stderr
    assert "could not ask:" not in stderr


@pytest.mark.parametrize("command", ["show", "approve", "reject"])
def test_a_reply_that_is_not_an_object_is_could_not_ask(replay, command):
    replay((200, [1, 2, 3]))
    code, stdout, stderr = run(command, *arguments())
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert "could not ask: answer_unreadable:" in stderr
    assert "Traceback" not in stderr


# -- misuse ------------------------------------------------------------------


@pytest.mark.parametrize("command", ["show", "approve", "reject"])
def test_missing_approval_reference_is_a_usage_error(command):
    with pytest.raises(SystemExit) as failure:
        run(command, "--scope", "team-ops", "--socket", "daemon.sock")
    assert failure.value.code == exit_codes.EXIT_PARSER_USAGE


@pytest.mark.parametrize("command", ["show", "approve", "reject"])
def test_missing_scope_is_a_usage_error(command):
    with pytest.raises(SystemExit) as failure:
        run(command, "--approval", "approval-1", "--socket", "daemon.sock")
    assert failure.value.code == exit_codes.EXIT_PARSER_USAGE


@pytest.mark.parametrize("command", ["show", "approve", "reject"])
def test_invalid_profile_is_misuse(command):
    code, stdout, stderr = run(command, *arguments("--mode", "system"))
    assert code == exit_codes.EXIT_MISUSE
    assert stdout == ""
    assert "names the account" in stderr


@pytest.mark.parametrize("command", ["show", "approve", "reject"])
def test_a_refused_request_exits_three_for_every_sub_command(replay, command):
    """A refusal the registry classes as such — the peer not admitted — is exit 3,
    like every other read of this client (article 1: distinct results, distinct codes)."""
    replay((403, problem("peer_not_admitted")))
    code, stdout, stderr = run(command, *arguments())
    assert code == exit_codes.EXIT_REFUSED, (stdout, stderr)
    assert stdout == ""
    assert "peer_not_admitted" in stderr
