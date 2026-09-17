# SPDX-License-Identifier: Apache-2.0
"""The walking skeleton: one question, over a real socket, rendered and exited.

Every test here runs the command the way a person runs it — argument list in,
process exit code out — over an actual `AF_UNIX` socket that an actual server
process-side object is listening on. Nothing is patched, and no client method is
called directly: what is proven is the path, not the pieces.

The scenarios are the contract's own golden set (article 13), which is what
makes these tests a claim about the contract rather than about this repository's
idea of it. Where a scenario cannot be arranged with the contract's fake — a
refused peer, an outcome this generation does not know — a socket answering that
exact document stands in, because both are answers a real daemon may give and
both have a rule this client must obey.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from canned_daemon import answering
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.golden import load_scenarios
from sayfirst_contract_stub.stub import Stub
from sayfirst_contract_stub.stub_http import serve

from sayfirst_cli import exit_codes
from sayfirst_cli.ask import main


def run(*argv: str) -> tuple[int, str, str]:
    """Run the command and return exactly what a shell would see."""
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def daemon(tmp_path: Path):
    """A socket serving the contract's fake, arranged for one golden scenario.

    The address does **not** carry the scenario name. `AF_UNIX` bounds an address
    at 108 bytes and the contract requires a fixture to leave 16 of them free
    (`ADDRESS_MARGIN_BYTES`, so that a third party replaying this suite on a host
    with a longer temporary root is not the one who discovers the limit). A
    temporary directory plus the longest scenario name this contract publishes —
    `policy_unavailable_is_could_not_ask` — spends the whole budget and the fake
    refuses to bind, which is the fake being right. The scenario is named where
    it is read, in the stub; the address is a short unique name per socket.
    """
    scenarios = load_scenarios()
    bound = 0

    def arrange(name: str):
        nonlocal bound
        stub = Stub(name, scenarios={name: scenarios[name]})
        bound += 1
        return serve(stub, tmp_path / f"d{bound}.sock")

    return arrange


@pytest.mark.parametrize(
    ("scenario", "outcome", "code"),
    [
        ("allow", "allow", exit_codes.EXIT_ALLOW),
        ("deny", "deny", exit_codes.EXIT_DENY),
        ("missing_policy", "deny", exit_codes.EXIT_DENY),
        ("review_approve", "suspend", exit_codes.EXIT_SUSPEND),
    ],
)
def test_each_outcome_is_rendered_and_exited_as_itself(
    daemon, scenario: str, outcome: str, code: int
) -> None:
    """Article 1: the three outcomes are closed, and each leaves its own trace."""
    with daemon(scenario) as socket_path:
        exit_code, stdout, stderr = run(
            "--capability", "example.effect", "--scope", "local", "--socket", str(socket_path)
        )
    assert exit_code == code, (scenario, stdout, stderr)
    assert f"outcome: {outcome}\n" in stdout
    assert "verified: true" in stdout
    assert stderr == ""


def test_the_answer_is_rendered_in_the_words_the_control_plane_used(daemon) -> None:
    """Article 1: this client explains the answer; it does not restate it."""
    with daemon("deny") as socket_path:
        exit_code, stdout, _ = run(
            "--capability", "example.effect", "--socket", str(socket_path), "--json"
        )
    assert exit_code == exit_codes.EXIT_DENY
    envelope = json.loads(stdout)
    assert envelope["result"]["outcome"] == "deny"
    assert envelope["result"]["reason"] == "policy_denies"
    assert envelope["result"]["authority"] == "authoritative"
    assert envelope["contract_generation"] == CONTRACT_GENERATION
    # What this process verified is kept apart from what the daemon said.
    assert envelope["verification"] == {
        "server_uid": os.geteuid(),
        "expected": os.geteuid(),
        "verified": True,
    }


def test_an_unavailable_policy_is_could_not_ask_and_never_a_denial(daemon) -> None:
    """Articles 1 and 2: "could not ask" is never written as denied or allowed."""
    with daemon("policy_unavailable_is_could_not_ask") as socket_path:
        exit_code, stdout, stderr = run(
            "--capability", "example.effect", "--socket", str(socket_path)
        )
    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK
    assert exit_code != exit_codes.EXIT_DENY
    assert "could not ask: policy_unavailable" in stderr
    assert "deny" not in stderr and "allow" not in stderr
    assert stdout == ""


def test_an_absent_daemon_is_could_not_ask(tmp_path: Path) -> None:
    """Article 1: an effect that has not started does not start, and says why."""
    exit_code, stdout, stderr = run(
        "--capability", "example.effect", "--socket", str(tmp_path / "absent.sock")
    )
    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK
    assert "could not ask: unreachable" in stderr
    assert "verified: false" in stderr
    assert stdout == ""


def test_a_server_that_is_not_the_daemon_principal_gets_no_bytes(daemon) -> None:
    """Article 6: the far end is verified before anything is written to it.

    The profile is told the daemon runs as another account, so the credential the
    kernel reports cannot match. The result is "could not ask" and not a denial:
    no answer about the effect exists (article 1).
    """
    if os.geteuid() == 0:
        pytest.skip("this test needs an account that is not the one running the fake")
    with daemon("allow") as socket_path:
        exit_code, stdout, stderr = run(
            "--capability",
            "example.effect",
            "--socket",
            str(socket_path),
            "--mode",
            "system",
            "--daemon-user",
            "root",
        )
    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK
    assert "could not ask: server_not_the_daemon_principal" in stderr
    assert stdout == ""


def test_an_outcome_this_generation_does_not_know_stops_the_effect(tmp_path: Path) -> None:
    """Article 13: an unknown outcome is reported as unknown, never as a denial."""
    document = {
        "contract_generation": CONTRACT_GENERATION,
        "authority": "authoritative",
        "decision_ref": "decision-1",
        "scope": "local",
        "capability": "example.effect",
        "outcome": "quarantine",
        "reason": "policy_allows",
        "policy_version": None,
        "approval_ref": None,
        "decided_at": "2026-09-04T00:00:00+00:00",
        "correlation": None,
    }
    with answering(tmp_path / "future.sock", 200, document) as socket_path:
        exit_code, stdout, stderr = run(
            "--capability", "example.effect", "--socket", str(socket_path)
        )
    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK
    assert "could not ask: outcome_unknown" in stderr
    assert "quarantine" in stderr
    assert stdout == ""


def test_a_refused_request_is_neither_an_answer_nor_an_absent_answer(tmp_path: Path) -> None:
    """Article 1: a refusal is its own result, with an exit code of its own."""
    document = {
        "contract_generation": CONTRACT_GENERATION,
        "code": "peer_not_admitted",
        "message": "this peer is not admitted to the host boundary",
        "retryable": False,
    }
    with answering(tmp_path / "refusing.sock", 403, document) as socket_path:
        exit_code, stdout, stderr = run(
            "--capability", "example.effect", "--socket", str(socket_path)
        )
    assert exit_code == exit_codes.EXIT_REFUSED
    assert exit_code not in {exit_codes.EXIT_DENY, exit_codes.EXIT_COULD_NOT_ASK}
    assert "refused: peer_not_admitted" in stderr
    assert stdout == ""


def test_a_system_profile_that_names_no_account_is_a_misuse(tmp_path: Path) -> None:
    """Article 6: a system profile that cannot say what it verifies is not one."""
    exit_code, stdout, stderr = run(
        "--capability", "example.effect", "--socket", str(tmp_path / "s.sock"), "--mode", "system"
    )
    assert exit_code == exit_codes.EXIT_MISUSE
    assert "names the account" in stderr
    assert stdout == ""


def test_the_command_takes_no_url_and_no_credential() -> None:
    """Article 6: there is no network to name and no token to hand over."""
    from sayfirst_cli.ask import build_parser

    options = {option for action in build_parser()._actions for option in action.option_strings}
    assert "--url" not in options
    assert not any("token" in option for option in options)
    assert "--socket" in options


@pytest.mark.parametrize("body", [[1, 2, 3], "x", 5, None])
def test_an_answer_that_is_not_a_document_is_could_not_ask(tmp_path: Path, body) -> None:
    """A 200 whose body is JSON but not a decision document is « could not ask » (exit 4),
    never a traceback — exit 1 is this client's published code for « deny »."""
    with answering(tmp_path / "odd.sock", 200, body) as socket_path:
        exit_code, stdout, stderr = run(
            "--capability", "example.effect", "--socket", str(socket_path)
        )
    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK
    assert "could not ask: answer_unreadable" in stderr
    assert "Traceback" not in stderr
    assert stdout == ""
