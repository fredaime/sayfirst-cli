# SPDX-License-Identifier: Apache-2.0
"""Read a decision's reason, rule and policy version in the plane's own words."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from . import reads, render


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sayfirst explain", description="Read the record and reason of a decision."
    )
    reads.add_connection_arguments(parser)
    parser.add_argument("--decision", required=True, help="the reference of the recorded decision")
    return parser


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    stdout, stderr = out or sys.stdout, err or sys.stderr
    arguments = build_parser().parse_args(argv)
    connection = reads.open_connection(arguments, stderr)
    if isinstance(connection, int):
        return connection
    try:
        result = reads.read(lambda: connection.read_decision(arguments.scope, arguments.decision))
        return reads.finish(result, arguments, connection, stdout, stderr, render.write_record)
    finally:
        connection.close()
