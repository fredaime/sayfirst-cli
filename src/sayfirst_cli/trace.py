# SPDX-License-Identifier: Apache-2.0
"""Read a decision and locate its first effect entry within a bounded evidence read."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from sayfirst_contract.client import Answered, Result
from sayfirst_contract.generation import CONTRACT_GENERATION

from . import pages, reads, render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sayfirst trace", description="Read a decision and its position in scoped evidence."
    )
    reads.add_connection_arguments(parser)
    parser.add_argument("--decision", required=True, help="the reference of the recorded decision")
    parser.add_argument(
        "--pages", type=reads.positive, default=10, help="the maximum number of evidence pages"
    )
    return parser


def _write_trace(document: Mapping[str, object], stream: TextIO) -> None:
    render.write_record({key: value for key, value in document.items() if key != "chain"}, stream)
    render.write_chain_position(document["chain"], stream)


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    stdout, stderr = out or sys.stdout, err or sys.stderr
    arguments = build_parser().parse_args(argv)
    connection = reads.open_connection(arguments, stderr)
    if isinstance(connection, int):
        return connection

    def walk() -> Result[Mapping[str, object]]:
        """The record, then the pages, then where in the chain the decision sits."""
        result = connection.read_decision(arguments.scope, arguments.decision)
        if not isinstance(result, Answered):
            return result
        record = result.value.to_document()
        from_sequence, read_pages, position = 1, 0, None
        for _ in range(arguments.pages):
            # The daemon closes the connection after a decision read (an adapter
            # wrote that answer), and an evidence read may close its own. The
            # transport never re-opens an address on a caller's behalf (rule
            # C4), so every page is read on a connection reopened — and the far
            # end verified again — here, exactly as `history` walks its pages.
            connection.reconnect()
            page = connection.read_evidence(arguments.scope, from_sequence, 100)
            if not isinstance(page, Answered):
                return page
            read_pages += 1
            entries, verification, next_from = pages.members(page.value, from_sequence)
            for entry in entries:
                if entry["kind"] == "effect" and entry["body"]["decision_id"] == arguments.decision:
                    grade = next(
                        (
                            item["grade"]
                            for item in verification["grades"]
                            if item["connection_id"] == entry["connection_id"]
                        ),
                        "unknown",
                    )
                    position = {
                        "sequence": entry["sequence"],
                        "entry_hash": entry["entry_hash"],
                        "grade": grade,
                    }
                    break
            if position is not None or next_from is None:
                break
            from_sequence = next_from
        if position is None:
            position = {"found": False, "pages": read_pages}
        return Answered({**record, "chain": position}, CONTRACT_GENERATION)

    try:
        return reads.finish(reads.read(walk), arguments, connection, stdout, stderr, _write_trace)
    finally:
        connection.close()
