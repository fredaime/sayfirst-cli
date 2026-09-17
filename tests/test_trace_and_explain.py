# SPDX-License-Identifier: Apache-2.0
"""Read records through the command tree and the contract's verified socket."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from canned_daemon import answering_by_path, hanging_up_after_accept
from documents import chain_page, problem
from sayfirst_contract.generation import CONTRACT_GENERATION

from sayfirst_cli import exit_codes
from sayfirst_cli.main import main


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_explain_renders_the_denied_record_and_exits_zero(tmp_path: Path, record) -> None:
    with answering_by_path(tmp_path / "d.sock", {"/decisions/": (200, record)}) as address:
        code, stdout, stderr = run(
            "explain", "--scope", "team-ops", "--decision", "decision-1", "--socket", str(address)
        )
    assert code == 0
    assert "outcome: deny\n" in stdout
    assert "reason: policy_denies\n" in stdout
    assert "rule_id: deny-one\n" in stdout
    assert "policy_version: policy-1\n" in stdout
    assert "verified: true" not in stdout
    assert stderr == ""


def test_explain_json_preserves_the_whole_record(tmp_path: Path, record) -> None:
    with answering_by_path(tmp_path / "d.sock", {"/decisions/": (200, record)}) as address:
        code, stdout, stderr = run(
            "explain",
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            str(address),
            "--json",
        )
    assert code == 0
    envelope = json.loads(stdout)
    assert envelope["result"] == record
    assert envelope["contract_generation"] == CONTRACT_GENERATION
    assert envelope["verification"] == {
        "server_uid": os.geteuid(),
        "expected": os.geteuid(),
        "verified": True,
    }
    assert stderr == ""


@pytest.mark.parametrize("command", ["trace", "explain"])
def test_reads_require_an_explicit_scope(command: str) -> None:
    with pytest.raises(SystemExit) as failure:
        run(command, "--decision", "decision-1", "--socket", "absent.sock")
    assert failure.value.code == 2


@pytest.mark.parametrize("command", ["trace", "explain"])
def test_missing_record_is_a_refusal(tmp_path: Path, command: str) -> None:
    """The daemon looked in the scope it was given and answered that it keeps no
    such record. That is a verdict on the question, which the contract's registry
    publishes as a refusal, so this client renders it as one — and never as a
    denial, which is what the policy said about an effect (article 1)."""
    routes = {"/decisions/": (404, problem("decision_not_found"))}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            command, "--scope", "team-ops", "--decision", "missing", "--socket", str(address)
        )
    assert code == exit_codes.EXIT_REFUSED
    assert stdout == ""
    assert "refused: decision_not_found" in stderr
    assert "denied" not in stderr and "could not ask:" not in stderr


@pytest.mark.parametrize("command", ["trace", "explain"])
def test_absent_socket_is_could_not_ask(tmp_path: Path, command: str) -> None:
    code, stdout, stderr = run(
        command,
        "--scope",
        "team-ops",
        "--decision",
        "decision-1",
        "--socket",
        str(tmp_path / "absent.sock"),
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert "could not ask: unreachable" in stderr


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("grade", ["unverified", "unknown"])
def test_trace_finds_the_first_effect_on_the_second_page(
    tmp_path: Path,
    record,
    as_json: bool,
    grade: str,
) -> None:
    first, second = chain_page(next_from=3), chain_page(found=True)
    # An identically referenced non-effect and an unrelated effect are not matches.
    entry = second["entries"][0]
    first["entries"] = [
        {**entry, "kind": "grade", "sequence": 1},
        {**entry, "body": {**entry["body"], "decision_id": "another"}, "sequence": 2},
    ]
    second["entries"].append({**entry, "sequence": 4, "entry_hash": "4" * 64})
    if grade == "unknown":
        second["verification"]["grades"] = [{"connection_id": "another", "grade": "unverified"}]
    routes = {"/decisions/": (200, record), "/scopes/": (200, [first, second])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            "trace",
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            str(address),
            *(["--json"] if as_json else []),
        )
    assert code == 0
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["result"] == {
            **record,
            "chain": {"sequence": 3, "entry_hash": "3" * 64, "grade": grade},
        }
        assert envelope["verification"]["verified"] is True
    else:
        assert f"chain: sequence 3, entry_hash {'3' * 64}, grade {grade}\n" in stdout
        assert "rule_id: deny-one\n" in stdout
    assert stderr == ""


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(("pages", "next_from", "read"), [(1, 3, 1), (10, None, 1), (10, 3, 10)])
def test_trace_reports_only_the_pages_read(
    tmp_path: Path,
    record,
    as_json: bool,
    pages: int,
    next_from: int | None,
    read: int,
) -> None:
    # Each page advances the read. A page repeating the sequence it answered is
    # not a continuation and is refused as unreadable, so a walk of ten pages is
    # ten pages of a chain rather than one page read ten times.
    served = (
        chain_page(next_from=next_from)
        if read == 1
        else [chain_page(next_from=index) for index in range(2, 2 + read)]
    )
    routes = {"/decisions/": (200, record), "/scopes/": (200, served)}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            "trace",
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            str(address),
            "--pages",
            str(pages),
            *(["--json"] if as_json else []),
        )
    assert code == 0
    if as_json:
        assert json.loads(stdout)["result"] == {**record, "chain": {"found": False, "pages": read}}
    else:
        assert f"chain: not found within {read} page(s)\n" in stdout
    assert stderr == ""


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    ("status", "problem_code", "expected"),
    [
        (403, "peer_not_admitted", exit_codes.EXIT_REFUSED),
        (503, "evidence_store_unavailable", exit_codes.EXIT_COULD_NOT_ASK),
    ],
)
def test_failed_page_is_never_rendered_as_not_found(
    tmp_path: Path,
    record,
    as_json: bool,
    status: int,
    problem_code: str,
    expected: int,
) -> None:
    routes = {"/decisions/": (200, record), "/scopes/": (status, problem(problem_code))}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            "trace",
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            str(address),
            *(["--json"] if as_json else []),
        )
    assert code == expected
    assert stdout == ""
    assert problem_code in stderr
    assert "chain:" not in stdout + stderr
    if as_json:
        assert "result" not in json.loads(stderr)
        assert json.loads(stderr)["verification"]["verified"] is True


@pytest.mark.parametrize("command", ["trace", "explain"])
def test_connection_loss_is_could_not_ask(tmp_path: Path, command: str) -> None:
    with hanging_up_after_accept(tmp_path / "d.sock") as address:
        code, stdout, stderr = run(
            command,
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            str(address),
            "--json",
        )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert json.loads(stderr)["problem"]["code"] == "unreachable"
    assert json.loads(stderr)["verification"]["verified"] is True


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    ("member", "value", "problem_member"),
    [
        pytest.param("entries", ..., "entries", id="missing-entries"),
        pytest.param("entries", None, "entries", id="null-entries"),
        pytest.param("verification", {"grades": None}, "verification.grades", id="null-grades"),
        pytest.param("next_from", ..., "next_from", id="missing-next-from"),
        pytest.param("next_from", "3", "next_from", id="string-next-from"),
        pytest.param("next_from", True, "next_from", id="boolean-next-from"),
        pytest.param("next_from", 0, "next_from", id="zero-next-from"),
    ],
)
def test_unreadable_page_is_could_not_ask(
    tmp_path: Path,
    record,
    as_json: bool,
    member: str,
    value: object,
    problem_member: str,
) -> None:
    # A matching entry must not conceal unreadable verification. Empty pages
    # must state their continuation before trace can claim a bounded absence.
    document = chain_page(found=member == "verification")
    if value is ...:
        del document[member]
    else:
        document[member] = value
    routes = {"/decisions/": (200, record), "/scopes/": (200, document)}
    # answering_by_path exposes only the address, not the accepted connection.
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            "trace",
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            str(address),
            *(["--json"] if as_json else []),
        )
    assert code == 4
    assert stdout == ""
    assert "chain:" not in stderr
    assert "Traceback" not in stderr
    if as_json:
        envelope = json.loads(stderr)
        assert envelope["problem"]["code"] == "answer_unreadable"
        assert problem_member in envelope["problem"]["message"]
        assert envelope["problem"]["retryable"] is None  # the registry states none
        assert envelope["problem"]["contract_generation"] == CONTRACT_GENERATION
        assert envelope["verification"]["verified"] is True
        assert "result" not in envelope
    else:
        assert "could not ask: answer_unreadable:" in stderr
        assert problem_member in stderr
        assert "verified: true" in stderr
        assert "retryable: not stated" in stderr


def test_trace_survives_a_daemon_that_closes_after_every_answer(tmp_path: Path, record) -> None:
    """The real daemon closes the connection after a decision read; `trace` reads the
    chain afterwards on the same verified connection, so it reconnects (rule C4).
    Without that reconnect the page read is « could not ask » and no chain is found."""
    routes = {"/decisions/": (200, record), "/scopes/": (200, chain_page(found=True))}
    with answering_by_path(tmp_path / "d.sock", routes, close_after_each=True) as address:
        code, stdout, stderr = run(
            "trace", "--scope", "team-ops", "--decision", "decision-1", "--socket", str(address)
        )
    assert code == 0, (stdout, stderr)
    assert "chain: sequence " in stdout
    assert stderr == ""


@pytest.mark.parametrize("command", ["trace", "explain"])
def test_a_reply_that_is_not_an_object_never_reaches_the_shell_as_deny(
    tmp_path: Path, command: str
) -> None:
    """A `200` whose body is JSON but not an object is an answer this client could not
    read: exit 4, `answer_unreadable`, and no traceback. Exit 1 is « deny », and the
    contract's reader raises `AttributeError` on a list where an object was promised."""
    # A one-element sequence of routes serves that element as the whole body.
    routes = {"/decisions/": (200, [[1, 2, 3]])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            command, "--scope", "team-ops", "--decision", "decision-1", "--socket", str(address)
        )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert "could not ask: answer_unreadable:" in stderr
    assert "Traceback" not in stderr
    assert "denied" not in stderr and "refused:" not in stderr


@pytest.mark.parametrize("as_json", [False, True])
def test_a_page_that_does_not_advance_is_could_not_ask(
    tmp_path: Path, record, as_json: bool
) -> None:
    """A daemon answering a read from sequence 1 with `next_from: 1` has not given a
    continuation. Walking it again until the page budget runs out would end in « not
    found within 3 page(s) » with exit 0 — an absence the read never established."""
    routes = {"/decisions/": (200, record), "/scopes/": (200, chain_page(next_from=1))}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            "trace",
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            str(address),
            "--pages",
            "3",
            *(["--json"] if as_json else []),
        )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == ""
    assert "chain:" not in stderr
    assert "Traceback" not in stderr
    if as_json:
        problem_document = json.loads(stderr)["problem"]
        assert problem_document["code"] == "answer_unreadable"
        assert "next_from does not advance the read" in problem_document["message"]
    else:
        assert "next_from does not advance the read" in stderr


@pytest.mark.parametrize("pages", ["0", "-999"])
def test_a_page_bound_that_is_not_positive_is_a_usage_error(capsys, pages: str) -> None:
    """« not found within 0 page(s) » with exit 0 was a mistyped bound rendered as an
    established absence; every other numeric argument of the slice refuses one."""
    with pytest.raises(SystemExit) as failure:
        run(
            "trace",
            "--scope",
            "team-ops",
            "--decision",
            "decision-1",
            "--socket",
            "absent.sock",
            "--pages",
            pages,
        )
    assert failure.value.code == exit_codes.EXIT_PARSER_USAGE
    assert "must be a positive integer" in capsys.readouterr().err


def test_trace_walks_two_pages_against_a_daemon_that_closes_after_every_answer(
    tmp_path: Path, record
) -> None:
    """The daemon hangs up after each answer, and `history --all` walks on because it
    reconnects before every page. `trace` reads up to ten pages on one connection and
    has to do the same: without it the second page is « could not ask », rule C4
    holding correctly over a reconnect this client never asked for."""
    routes = {
        "/decisions/": (200, record),
        "/scopes/": (200, [chain_page(next_from=3), chain_page(found=True)]),
    }
    with answering_by_path(tmp_path / "d.sock", routes, close_after_each=True) as address:
        code, stdout, stderr = run(
            "trace", "--scope", "team-ops", "--decision", "decision-1", "--socket", str(address)
        )
    assert code == 0, (stdout, stderr)
    assert f"chain: sequence 3, entry_hash {'3' * 64}, grade unverified\n" in stdout
    assert stderr == ""
