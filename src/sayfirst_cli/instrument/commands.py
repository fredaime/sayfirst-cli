# SPDX-License-Identifier: Apache-2.0
"""`sayfirst instrument`: run somebody's program with the boundary in front of it.

Three verbs, because one word cannot carry two meanings. Article 9 writes
« `sayfirst instrument apply` executes it » while also making runtime
interposition the primary mode and a committed code modification a later option
— and a verb that undoes itself when the process ends is not the same act as a
verb that edits somebody's repository. `apply` is the ordinary name for the
second, so it keeps the article's name for the article's later option and says,
in as many words, that it is not that option yet (the architecture reading of
2026-09-14). Nothing is renamed into meaning its opposite, and a reader who
disagrees has an amendment to write rather than a redefinition to find in code.

The codes this command produces come from two places and never a third: the
invocation's own mistakes, which are this client's to report, and the governed
program's ending, which is the program's and is passed through untouched.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TextIO

from sayfirst_contract.client import Refused
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.transport.socket_client import (
    PER_USER,
    SYSTEM,
    ProfileMisuse,
    SocketClientProblem,
    SocketProfile,
)

from .. import exit_codes, reads, render
from . import engine, launch, manifest, verify

#: What `apply` says instead of doing anything. The sentence names the mode that
#: does exist, because a refusal that leaves the reader with no next step is
#: only half of what article 2 asks of an absence.
APPLY_REFUSAL: Final[str] = (
    "instrument apply is reserved for the committed code modification, which does not "
    "exist yet; use `instrument run`, the reversible mode (architecture reading, 2026-09-14)"
)

#: The verbs that do nothing, and the sentence each says instead. They are
#: answered before the parser reads their arguments, because they refuse the
#: ACT: a usage error about an option would suggest that some other spelling of
#: the same act would be accepted, and none would. `verify` left this table
#: when the verifier arrived; `apply` stays until the committed code
#: modification does.
RESERVED: Final[dict[str, str]] = {"apply": APPLY_REFUSAL}


def build_parser() -> argparse.ArgumentParser:
    """Every verb this command answers, and only the ones it answers."""
    parser = argparse.ArgumentParser(
        prog="sayfirst instrument",
        description="Run a program with the sayfirst boundary in front of named effects.",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)
    running = verbs.add_parser("run", help="run a program with the designated packs installed")
    running.add_argument(
        "--pack",
        action="append",
        required=True,
        metavar="DIR",
        help="a pack directory; repeat the option for each pack",
    )
    running.add_argument("--scope", required=True, help="the scope the questions are asked in")
    running.add_argument("--socket", required=True, help="the path of the daemon's socket")
    running.add_argument("--mode", choices=(PER_USER, SYSTEM), default=PER_USER)
    running.add_argument(
        "--daemon-user",
        default=None,
        help="the account the daemon runs as; a system profile names it",
    )
    running.add_argument(
        "--principal",
        default=None,
        metavar="REF",
        help="the principal reference to hold grants against; this account by default",
    )
    running.add_argument(
        "target",
        nargs="*",
        metavar="TARGET",
        help="after `--`: either -m MODULE [args] or SCRIPT [args]",
    )
    verify.add_arguments(
        verbs.add_parser("verify", help="prove every named effect of a program was decided")
    )
    # Declared so that `--help` names every verb this command answers, article 2's
    # rule about a help text being a claim. `main` answers this one before the
    # parser is asked to read anything after it.
    verbs.add_parser("apply", help="the committed code modification (reserved; it refuses)")
    return parser


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    """Run the verb and return the code the calling shell should see."""
    stdout = out or sys.stdout
    stderr = err or sys.stderr
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if forwarded and forwarded[0] in RESERVED:
        stderr.write(f"{RESERVED[forwarded[0]]}\n")
        return exit_codes.EXIT_MISUSE
    return _run(build_parser().parse_args(forwarded), stdout, stderr)


def _run(arguments: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    """Read the packs, open the profile, and hand the program over.

    Everything that can be wrong with the invocation is found before a single
    attribute is replaced — with the one exception the engine names: an
    attribute a pack declares on a module the program only imports later
    cannot be checked before that import, and is refused when it happens. A
    program half instrumented would be running partly governed with nothing
    saying which part, which is worse than not running.
    """
    if arguments.verb == "verify":
        # Layer 3 owns its own codes: they are about the proof, never about the
        # program's ending, which `run` below is the one that passes through.
        return verify.run(arguments, stdout, stderr)
    packs: list[manifest.Pack] = []
    for named in arguments.pack:
        try:
            packs.append(manifest.read_pack(Path(named)))
        except manifest.PackInvalid as invalid:
            # The path as it was TYPED, not as it was resolved: with more than
            # one `--pack` the sentence alone does not say which one to fix, and
            # a resolved path is not what the reader has in their shell history.
            stderr.write(f"{named}: {invalid}\n")
            return exit_codes.EXIT_MISUSE
    try:
        profile = SocketProfile(
            arguments.socket,
            mode=arguments.mode,
            daemon_user=arguments.daemon_user,
            scope=arguments.scope,
        )
    except ProfileMisuse as invalid:
        stderr.write(f"{invalid}\n")
        return exit_codes.EXIT_MISUSE
    try:
        return launch.run(
            packs,
            profile,
            arguments.target,
            principal=arguments.principal,
            out=stdout,
            err=stderr,
        )
    except launch.LaunchMisuse as misuse:
        # Everything the launcher refuses BEFORE the hand-off: a point the
        # engine will not install, an execution module that will not load, a
        # target that names no program. The program has not started, so this is
        # the invocation's mistake and not an outcome about an effect.
        stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    except engine.EngineMisuse as misuse:
        # A point naming an attribute a module does not have, discovered inside
        # the program's own import — the one check that cannot be made before
        # the hand-off (the engine says why). The pack is the invocation's and
        # the program is innocent: no question was ever put, so it is 64, the
        # same answer this file already gives the byte-identical shape of a
        # `-m` name that resolves to a package with no `__main__`. Uncaught, it
        # reached a shell as a traceback and exit 1, this client's published
        # code for « deny », over a mistake the plane was never asked about.
        stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    except SocketClientProblem as failure:
        # Raised while the connection was being arranged, so no question was
        # ever put. It is reported with the contract's own classification and
        # never as a denial (articles 1 and 2); a refusal the boundary raises
        # later, inside the program, is the program's and is not caught here.
        return _write_problem(failure, stderr)


def _write_problem(failure: SocketClientProblem, stderr: TextIO) -> int:
    """A non-answer, said as the reads say it, with the code the reads use."""
    result = reads.connection_problem(failure)
    could_not_ask = not isinstance(result, Refused)
    render.write_problem(
        result.problem.to_document(CONTRACT_GENERATION), stderr, could_not_ask=could_not_ask
    )
    return exit_codes.EXIT_COULD_NOT_ASK if could_not_ask else exit_codes.EXIT_REFUSED
