# SPDX-License-Identifier: Apache-2.0
"""The shared path for scoped reads: verify the connection and render its result.

A read acts for nobody and carries no delegation. Its success says a record
was read, never that the effect recorded there may be exercised (article 1).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from typing import Final, Protocol, TextIO

from sayfirst_contract.client import Answered, CouldNotAsk, Refused, Result
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.problems import Problem, ProblemCode, problem_retryable
from sayfirst_contract.transport.socket_client import (
    PER_USER,
    SYSTEM,
    ProfileMisuse,
    SocketClientProblem,
    SocketProfile,
    VerifiedConnection,
    connect,
)

from . import exit_codes, render

INPUT_ERRORS: Final = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    OverflowError,
    RecursionError,
)
"""The exceptions an answer from the daemon can raise on its way into this client.

The contract's readers classify what they can and let the rest through: a `200`
whose body is JSON but not an object raises `AttributeError` inside
`read_decision`, a reply nested past the interpreter's limit raises
`RecursionError` inside `json.loads`, a timestamp outside the calendar raises
`OverflowError`. Every one of them is an answer this client could not read —
« could not ask », never « denied » (articles 1 and 2) — and an escape from here
ends the process with a traceback, exit 1, which is this client's code for deny.
One tuple, because five copies of it is how a sixth caller comes to spell none.
"""

DOCUMENT_DEPTH_LIMIT: Final = 64
"""How deeply nested a daemon document may be before this client declines to read it.

A real record, page or bundle nests a handful of levels (entries, bodies,
attached policies). A document nested thousands deep still parses, and then the
step that renders it back into an envelope exhausts the interpreter and ends the
process with a traceback — exit 1, deny again. A bound stated here is honest; an
escape is not.

**The bound is measured where the render happens**, which is `finish` below: it
is the whole answer a command composes, not one page of it, that the envelope is
built from. `PAGE_DEPTH_LIMIT` is the same rule read one step earlier, so that a
page a walk accepts is a page the command that walks it can render.
"""

PAGE_DEPTH_LIMIT: Final = DOCUMENT_DEPTH_LIMIT - 2
"""How deeply nested ONE page may be, which is two levels shallower, and why.

A paging read hands `finish` the pages it collected under a member of its own —
`{"pages": [page, …]}` — so every page sits three levels down in the answer that
is actually rendered, and its own deepest member two levels deeper than it
measured alone. A page validator that used the full bound therefore accepted
pages the render then refused, after the prose for the pages before it had
already reached the caller: half an answer and then « could not ask » is worse
than either answer alone.

**One rule, one number, subtracted once, and measured rather than argued.** The
`2` is not a margin: it is the exact difference between the two documents, and
`tests/test_evidence_history_and_audit.py`'s bound pair is what pins it — a page
at the full bound renders as an answer, and one level past it is refused before
a byte reaches stdout. A subtraction that drifted in either direction turns one
of those two red. A caller composing a different answer around a page passes its
own limit to `too_deep`, which is why that argument exists; nothing else is
bounded twice.
"""


class DocumentValue(Protocol):
    """A typed contract value that supplies its own document."""

    def to_document(self) -> Mapping[str, object]: ...


def positive(value: str) -> int:
    """A bound a caller supplies: zero and below are misuse, not a small read.

    One rule across the slice, because `--pages 0` claiming « not found within 0
    page(s) » with exit 0 is a mistyped bound rendered as an established absence.
    """
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def too_deep(value: object, limit: int = DOCUMENT_DEPTH_LIMIT) -> bool:
    """Whether a document nests beyond `limit` — iteratively, so the check itself
    can never be the recursion it guards against.

    The default is the bound on a whole answer; a caller bounding one piece of
    one passes `PAGE_DEPTH_LIMIT` and says which piece in its own refusal.
    """
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if depth > limit:
            return True
        if isinstance(item, Mapping):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return False


def unreadable(failure: Exception) -> CouldNotAsk:
    """An answer this client could not read, said as that and never as a refusal."""
    return CouldNotAsk(
        # Retryability is the registry's to state, never this client's: the
        # contract's table says « not stated » for an unreadable answer, and the
        # transport says the same when it is the one that classifies (article 2).
        Problem(
            ProblemCode.ANSWER_UNREADABLE,
            str(failure),
            problem_retryable(ProblemCode.ANSWER_UNREADABLE),
            CONTRACT_GENERATION,
        )
    )


def read[T](operation: Callable[[], Result[T]]) -> Result[T]:
    """Run one read of the daemon: the two ways an answer fails to be one, in one place.

    A transport failure carries the contract's own classification — refused, or
    could not ask. An answer that arrives and cannot be read is
    `answer_unreadable`. Neither is a decision, and neither may reach the shell
    as exit 1, the code for « deny ». Every read of this client goes through
    here, a page walk included, so that a command cannot be the one that forgot.
    """
    try:
        return operation()
    except SocketClientProblem as failure:
        return connection_problem(failure)
    except INPUT_ERRORS as failure:
        return unreadable(failure)


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    """Every read names its scope explicitly, with the writer's connection options."""
    parser.add_argument("--scope", required=True, help="the scope the question is asked in")
    parser.add_argument("--socket", required=True, help="the path of the daemon's socket")
    parser.add_argument("--mode", choices=(PER_USER, SYSTEM), default=PER_USER)
    parser.add_argument(
        "--daemon-user",
        default=None,
        help="the account the daemon runs as; a system profile names it",
    )
    parser.add_argument("--json", action="store_true", help="write the envelope instead of prose")


def connection_problem(failure: SocketClientProblem) -> Refused | CouldNotAsk:
    """A transport exception is a non-answer, with the contract's classification."""
    if failure.classification == "refused":
        return Refused(failure.problem)
    return CouldNotAsk(failure.problem)


def open_connection(arguments: argparse.Namespace, stderr: TextIO) -> VerifiedConnection | int:
    """Verify the daemon, or report why this invocation could not open a connection."""
    try:
        profile = SocketProfile(
            arguments.socket,
            mode=arguments.mode,
            daemon_user=arguments.daemon_user,
            scope=arguments.scope,
        )
    except ProfileMisuse as misuse:
        stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    try:
        return connect(profile)
    except SocketClientProblem as failure:
        return _write_problem(
            connection_problem(failure),
            arguments,
            render.verification_document(None, None, False),
            stderr,
        )


def finish(
    result: Result[DocumentValue | Mapping[str, object]],
    arguments: argparse.Namespace,
    connection: VerifiedConnection,
    stdout: TextIO,
    stderr: TextIO,
    render_answer: Callable[[Mapping[str, object], TextIO], None],
) -> int:
    """Render the supplied record or problem; a record's outcome is only data."""
    verification = render.verification_document(
        connection.server_credential.uid, connection.expected_uid, connection.verified
    )
    # The document is materialised and bounded through the same helper the read
    # used: `to_document` is itself a step an unreadable answer raises inside,
    # and the render below is the step a document nested past the bound would
    # overflow. Either way the answer is one this client could not read.
    answer = read(lambda: _bounded(result)) if isinstance(result, Answered) else result
    if isinstance(answer, Answered):
        document = answer.value
        if arguments.json:
            render.write_json(
                render.envelope(CONTRACT_GENERATION, verification, result=document), stdout
            )
        else:
            render_answer(document, stdout)
        return 0
    return _write_problem(answer, arguments, verification, stderr)


def _bounded(
    result: Answered[DocumentValue | Mapping[str, object]],
) -> Answered[Mapping[str, object]]:
    """The answer as the document about to be rendered, refused if it nests too deep."""
    value = result.value
    document = value if isinstance(value, Mapping) else value.to_document()
    if too_deep(document):
        raise ValueError(
            f"nested deeper than {DOCUMENT_DEPTH_LIMIT} levels; not a document this client reads"
        )
    return Answered(document, result.contract_generation)


def _write_problem(
    result: Refused | CouldNotAsk,
    arguments: argparse.Namespace,
    verification: Mapping[str, object],
    stderr: TextIO,
) -> int:
    could_not_ask = not isinstance(result, Refused)
    problem = result.problem.to_document(CONTRACT_GENERATION)
    document = render.envelope(CONTRACT_GENERATION, verification, problem=problem)
    if arguments.json:
        render.write_json(document, stderr)
    else:
        render.write_verification(verification, stderr)
        render.write_problem(problem, stderr, could_not_ask=could_not_ask)
    return exit_codes.EXIT_COULD_NOT_ASK if could_not_ask else exit_codes.EXIT_REFUSED
