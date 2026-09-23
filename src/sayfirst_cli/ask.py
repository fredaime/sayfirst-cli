# SPDX-License-Identifier: Apache-2.0
"""`sayfirst ask`: put one question to the control plane and render its answer.

This is the product act. A person names a capability and a scope, this client
opens the daemon's socket, verifies the far end is the daemon's principal before
it writes anything, sends the question the contract defines, and renders the
answer the control plane gave — `allow`, `deny` or `suspend` — with an exit code
per outcome.

What this command does **not** do is the point of it. It holds no policy, it
caches no decision, and when the daemon cannot be reached it says so; it never
turns "could not ask" into "deny" and never turns it into "allow" (articles 1
and 2). There is no `--url` and nothing that takes a token: the boundary says
who the caller is, and it says so from the socket (article 6).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final, TextIO

from sayfirst_contract.client import Answered, Refused
from sayfirst_contract.decisions import DecisionAsk, Outcome
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.problems import REFUSED
from sayfirst_contract.transport.socket_client import (
    PER_USER,
    SYSTEM,
    ProfileMisuse,
    SocketClientProblem,
    SocketProfile,
    connect,
    declared_delegation,
)

from . import exit_codes, reads, render

#: One exit code per outcome the contract defines. `tests/test_exit_codes.py`
#: holds this map against `Outcome`, so the fallback below is unreachable in a
#: build whose contract and client agree.
EXIT_BY_OUTCOME: Final[dict[Outcome, int]] = {
    Outcome.ALLOW: exit_codes.EXIT_ALLOW,
    Outcome.DENY: exit_codes.EXIT_DENY,
    Outcome.SUSPEND: exit_codes.EXIT_SUSPEND,
}


def build_parser() -> argparse.ArgumentParser:
    """Every option this command accepts. None of them names a network."""
    parser = argparse.ArgumentParser(
        prog="sayfirst ask",
        description="Ask the control plane whether one capability may be exercised.",
    )
    parser.add_argument("--capability", required=True, help="the kind of effect, and nothing more")
    parser.add_argument("--scope", default="local", help="the scope the question is asked in")
    reads.add_socket_argument(parser)
    parser.add_argument("--mode", choices=(PER_USER, SYSTEM), default=PER_USER)
    parser.add_argument(
        "--daemon-user",
        default=None,
        help="the account the daemon runs as; a system profile names it",
    )
    parser.add_argument("--arguments-digest", default=None)
    parser.add_argument("--correlation", default=None)
    parser.add_argument("--json", action="store_true", help="write the envelope instead of prose")
    return parser


def _exit_for_answer(outcome: Outcome) -> int:
    """The code for an outcome, failing closed on one this client cannot render.

    An outcome the contract defines and this map has forgotten is a defect of
    this file, not an answer: it is reported the way an unreadable answer is,
    because the one thing it must never do is exit zero (articles 1 and 3).
    """
    return EXIT_BY_OUTCOME.get(outcome, exit_codes.EXIT_COULD_NOT_ASK)


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    """Run the command and return the code the calling shell should see."""
    stdout = out or sys.stdout
    stderr = err or sys.stderr
    arguments = build_parser().parse_args(argv)

    try:
        address = reads.address_of(arguments)
        profile = SocketProfile(
            address.path,
            mode=arguments.mode,
            daemon_user=arguments.daemon_user,
            scope=arguments.scope,
        )
    except ProfileMisuse as misuse:
        stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE

    # Declared by a privilege tool, never proven by it: article 6 keeps a
    # delegation visible instead of collapsing it into the human's identity.
    declared = declared_delegation()

    try:
        connection = connect(profile, timeout=reads.READ_TIMEOUT)
    except SocketClientProblem as failure:
        reads.say_where_it_looked(address, arguments, stderr)
        could_not_ask = failure.classification != REFUSED
        document = render.envelope(
            CONTRACT_GENERATION,
            render.verification_document(None, None, False),
            problem=failure.problem.to_document(CONTRACT_GENERATION),
        )
        _write(document, arguments.json, stderr, could_not_ask=could_not_ask)
        return exit_codes.EXIT_COULD_NOT_ASK if could_not_ask else exit_codes.EXIT_REFUSED

    try:
        ask = DecisionAsk(
            capability=arguments.capability,
            scope=arguments.scope,
            arguments_digest=arguments.arguments_digest,
            correlation=arguments.correlation,
        )
        # Read before the question is put, because it is already true: the far
        # end was verified before a byte was written, and it stays what was
        # verified whether or not an answer ever comes back.
        verification = render.verification_document(
            connection.server_credential.uid, connection.expected_uid, connection.verified
        )
        # A transport failure with the question already on the wire (a daemon
        # restarted, stopped or killed between the accept and the answer) and
        # an answer that arrived but is not a decision document are both
        # non-answers: nothing is reported as an answer, and neither reaches
        # the shell as a traceback — exit 1 is this client's published code
        # for `deny` (articles 1 and 2). The one rule lives beside the reads.
        result = reads.read(lambda: connection.ask_decision(ask, declared))
        if isinstance(result, Answered):
            # Bounded as every read is: a decision nested past what this client
            # reads is an answer it could not read, whatever its outcome says —
            # never a traceback, whose status 1 is this client's « deny ».
            rendered = reads.read(lambda: reads.bounded(result))
            if isinstance(rendered, Answered):
                document = render.envelope(
                    result.contract_generation, verification, result=rendered.value
                )
                _write(document, arguments.json, stdout)
                return _exit_for_answer(result.value.outcome)
            result = rendered
        could_not_ask = not isinstance(result, Refused)
        document = render.envelope(
            CONTRACT_GENERATION,
            verification,
            problem=result.problem.to_document(CONTRACT_GENERATION),
        )
        _write(document, arguments.json, stderr, could_not_ask=could_not_ask)
        return exit_codes.EXIT_COULD_NOT_ASK if could_not_ask else exit_codes.EXIT_REFUSED
    finally:
        connection.close()


def _write(
    document: dict[str, object], as_json: bool, stream: TextIO, *, could_not_ask: bool = False
) -> None:
    if as_json:
        render.write_json(document, stream)
        return
    verification = document["verification"]
    assert isinstance(verification, dict)
    render.write_verification(verification, stream)
    result = document.get("result")
    if isinstance(result, dict):
        render.write_decision(result, stream)
    problem = document.get("problem")
    if isinstance(problem, dict):
        render.write_problem(problem, stream, could_not_ask=could_not_ask)
