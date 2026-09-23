# SPDX-License-Identifier: Apache-2.0
"""Three bounds a client of a control plane must hold whatever the far end does.

- **A uid with no account.** A container started under an arbitrary uid has no
  account name to spell. The daemon names such a peer by its number, and the
  launcher's spelling must be the one it compares against — the launcher ended
  in a traceback and status 1 instead, this client's « deny ».
- **A far end that never answers.** `ask` and every read opened a connection
  with no bound, so a process that accepted it and then said nothing held the
  command for ever. They now wait a bounded time and report that the control
  plane could not be asked.
- **An answer nested past what this client reads.** A daemon may add members to
  a document the contract publishes, and `ask` rendered a decision with no
  depth bound: an `allow` nested thousands deep ended, on an interpreter whose
  encoder recurses, as a traceback and status 1. The reads already refuse such
  a document as one this client could not read; `ask` now applies the same rule.
"""

from __future__ import annotations

import io
import os
import socket
import time
from pathlib import Path

import pytest
from contract_absence import contract_is_installed, skip_without_the_contract


def test_a_uid_with_no_account_is_spelled_by_its_number(monkeypatch: pytest.MonkeyPatch) -> None:
    from sayfirst_cli.instrument import launch

    def no_account(uid: int) -> object:
        raise KeyError(f"getpwuid(): uid not found: {uid}")

    monkeypatch.setattr(launch.pwd, "getpwuid", no_account)
    assert launch.this_account() == f"user:{os.geteuid()}"


def test_ask_gives_up_on_a_far_end_that_never_answers(request, tmp_path: Path) -> None:
    if not contract_is_installed():
        skip_without_the_contract(request, "ask builds the contract's own client")
    from sayfirst_cli import ask, reads

    address = tmp_path / "daemon.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(address))
        server.listen(4)
        out, err = io.StringIO(), io.StringIO()
        started = time.monotonic()
        code = ask.main(
            ["--capability", "process.spawn", "--scope", "local", "--socket", str(address)],
            out=out,
            err=err,
        )
        elapsed = time.monotonic() - started
    assert code == 4, (out.getvalue(), err.getvalue())
    assert elapsed < reads.READ_TIMEOUT + 5.0, f"ask waited {elapsed:.1f}s"


def test_a_decision_nested_past_the_bound_is_an_answer_ask_could_not_read(
    request, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not contract_is_installed():
        skip_without_the_contract(request, "ask renders the contract's own decision")
    from sayfirst_contract.client import Answered
    from sayfirst_contract.decisions import Decision, Outcome, Reason

    from sayfirst_cli import ask

    deep: object = "bottom"
    for _ in range(1500):
        deep = {"x": deep}
    decision = Decision(
        decision_ref="dec-1",
        scope="local",
        capability="process.spawn",
        outcome=Outcome.ALLOW,
        reason=Reason.POLICY_ALLOWS,
        policy_version="sha256:" + "a" * 64,
        approval_ref=None,
        decided_at="2026-09-23T12:00:00+00:00",
        correlation=None,
        contract_generation=1,
        extra={"deep": deep},
    )

    class Credential:
        uid = os.geteuid()
        pid = 1

    class Connection:
        server_credential = Credential()
        expected_uid = os.geteuid()
        verified = True

        def ask_decision(self, question: object, declared: object) -> object:
            return Answered(decision, 1)

        def close(self) -> None: ...

    monkeypatch.setattr(ask, "connect", lambda profile, **_: Connection())
    out, err = io.StringIO(), io.StringIO()
    code = ask.main(
        ["--capability", "process.spawn", "--scope", "local", "--socket", "d.sock", "--json"],
        out=out,
        err=err,
    )
    assert code == 4, (out.getvalue(), err.getvalue())
    assert "Traceback" not in err.getvalue()
