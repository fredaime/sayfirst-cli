# SPDX-License-Identifier: Apache-2.0
"""The `sayfirst` command tree, for asking and reading what was decided.

The constitution names `sayfirst` as one command with subcommands, and one
console script points at one module. This distribution is the product client
(article 14), so it installs the script and dispatches; a later slice adds a
subcommand by adding it to the dispatch, never by claiming a second script.

`--help` lists exactly the commands this distribution answers, because a help
text that advertises an absent command is a claim without evidence (article 2).
It is answered from the table below and imports nothing, so the claim can be
read on a machine where the control plane's contract distribution is not
installed — which is where it is most likely to be asked.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable, Sequence
from typing import Final, TextIO

#: The subcommands this distribution answers, each with the module that owns its
#: parser and its exit codes, and whose `main` is its entry point. A slice adds
#: a line here.
#
# Named rather than imported, because `--help` is a claim about what this tool
# answers and answering it must not need the control plane's contract
# distribution installed: importing every subcommand up front made
# `python -m sayfirst_cli.main --help` a traceback wherever the contract is
# absent, and turned a reduced run's honest « not run » into failures (article
# 2's rule about an absence rendered as a negative fact, inverted).
COMMANDS: Final[dict[str, str]] = {
    "ask": "sayfirst_cli.ask",
    "trace": "sayfirst_cli.trace",
    "explain": "sayfirst_cli.explain",
    "evidence": "sayfirst_cli.evidence",
    "approvals": "sayfirst_cli.approvals",
    "instrument": "sayfirst_cli.instrument.commands",
    "packs": "sayfirst_cli.packs_cmd",
}


def entry_point(name: str) -> Callable[..., int]:
    """The `main` of one subcommand, imported when it is about to run and not before."""
    return importlib.import_module(COMMANDS[name]).main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sayfirst",
        description=("Ask the sayfirst control plane before an effect, and read what it decided."),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        # Declared so `--help` names every subcommand this tool answers. Each
        # subcommand's own parser reads its arguments, after the dispatch below.
        commands.add_parser(name, add_help=False)
    return parser


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if forwarded and forwarded[0] in COMMANDS:
        return entry_point(forwarded[0])(forwarded[1:], out=out, err=err)
    build_parser().parse_args(forwarded)
    raise AssertionError("argparse accepted a command that has no entry point")


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    run()
