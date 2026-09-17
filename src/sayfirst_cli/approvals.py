# SPDX-License-Identifier: Apache-2.0
"""Read a suspended request, approve it, reject it — one person, nothing more.

Article 12's simple form: no signatures, no designation, one person's act. This
module reads the same way `trace` and `explain` do — through `reads.read` and
`reads.finish` — because `show` is exactly that shape, and `approve`/`reject`
answer the same document a `show` would: the record the act left behind, so a
caller renders one writer whichever of the three it asked for.

Unlike `read_decision`, the daemon does NOT close the connection after
`read_approval` or `resolve_approval` (the transport's own docstrings say so):
it writes both answers through its own handler and leaves the connection for
the next request. That is what lets a person read a wait and then end it
without reconnecting — and it is the daemon's behaviour to rely on, not a
promise the daemon owes across every future release. One command here ever
does one thing, so nothing in this module reads twice on the same connection
and rule C4's explicit reconnect never comes up.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Final, TextIO

from sayfirst_contract.approvals import ApprovalResolution, Resolution

from . import reads, render


def _stated(value: object) -> str:
    """A member as a person reads it, with absence said rather than shown.

    The same rule `render._stated` applies, spelled here rather than imported:
    that helper is render's own, and a second module reaching into it is a
    second module that breaks when its name does.
    """
    return render.NOT_STATED if value is None else str(value)


def _write_approval(document: Mapping[str, object], stream: TextIO) -> None:
    """The seven members a person reads about one wait — read or resolved alike."""
    stream.write(f"approval: {document['approval_ref']}\n")
    stream.write(f"decision: {document['decision_ref']}\n")
    stream.write(f"state: {document['state']}\n")
    stream.write(f"requested_at: {document['requested_at']}\n")
    stream.write(f"deadline: {document['deadline']}\n")
    stream.write(f"resolved_at: {_stated(document.get('resolved_at'))}\n")
    stream.write(f"reason: {_stated(document.get('resolution_reason'))}\n")


def _connection_parser(prog: str) -> argparse.ArgumentParser:
    """Every `approvals` subcommand shares the connection options and `--approval`."""
    parser = argparse.ArgumentParser(prog=prog)
    reads.add_connection_arguments(parser)
    parser.add_argument("--approval", required=True, help="the reference of the suspended approval")
    return parser


def _show(argv: Sequence[str], *, out: TextIO, err: TextIO) -> int:
    parser = _connection_parser("sayfirst approvals show")
    arguments = parser.parse_args(argv)
    connection = reads.open_connection(arguments, err)
    if isinstance(connection, int):
        return connection
    try:
        result = reads.read(lambda: connection.read_approval(arguments.scope, arguments.approval))
        return reads.finish(result, arguments, connection, out, err, _write_approval)
    finally:
        connection.close()


def _resolve(argv: Sequence[str], *, out: TextIO, err: TextIO, resolution: Resolution) -> int:
    parser = _connection_parser(f"sayfirst approvals {resolution.value}")
    parser.add_argument("--reason", default=None, help="why this decision was made")
    arguments = parser.parse_args(argv)
    connection = reads.open_connection(arguments, err)
    if isinstance(connection, int):
        return connection
    try:
        act = ApprovalResolution(arguments.scope, arguments.approval, resolution, arguments.reason)
        # Put exactly once (the transport's own rule): a failure here is
        # reported as what the transport classified it, never retried by this
        # command on the caller's behalf.
        result = reads.read(lambda: connection.resolve_approval(act))
        return reads.finish(result, arguments, connection, out, err, _write_approval)
    finally:
        connection.close()


def _approve(argv: Sequence[str], *, out: TextIO, err: TextIO) -> int:
    return _resolve(argv, out=out, err=err, resolution=Resolution.APPROVE)


def _reject(argv: Sequence[str], *, out: TextIO, err: TextIO) -> int:
    return _resolve(argv, out=out, err=err, resolution=Resolution.REJECT)


#: The three acts this distribution answers, each with the entry point that
#: owns its parser and its exit codes.
COMMANDS: Final[dict[str, Callable[..., int]]] = {
    "show": _show,
    "approve": _approve,
    "reject": _reject,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sayfirst approvals",
        description="Read a suspended request, approve it, or reject it.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        commands.add_parser(name, add_help=False)
    return parser


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if forwarded and (command := COMMANDS.get(forwarded[0])) is not None:
        return command(forwarded[1:], out=out or sys.stdout, err=err or sys.stderr)
    build_parser().parse_args(forwarded)
    raise AssertionError("argparse accepted an approvals command that has no entry point")
