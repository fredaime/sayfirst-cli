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
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, TextIO

from sayfirst_boundary import AskRefused, BoundaryError, CouldNotAsk, Denied, Suspended
from sayfirst_contract.client import Refused
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.transport.socket_client import (
    PER_USER,
    SYSTEM,
    ProfileAddress,
    ProfileMisuse,
    SocketClientProblem,
    SocketProfile,
)

from .. import exit_codes, reads, render
from . import designation, engine, interpreter, launch, manifest, verify

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
        metavar="PACK",
        help=designation.HELP,
    )
    running.add_argument("--scope", required=True, help="the scope the questions are asked in")
    reads.add_socket_argument(running)
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
        "--follow-children",
        action="store_true",
        help=(
            "install the boundary in the Python children the program spawns with its "
            "environment, so their effects are governed as well; a child started with -S, -I "
            "or -E, or with a PYTHONPATH of its own, is not followed; needs this client "
            "installed in the interpreter the children run, and fails a child closed if it "
            "cannot"
        ),
    )
    running.add_argument(
        "target",
        nargs="*",
        metavar="TARGET",
        help=interpreter.TARGET_HELP,
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
    parser = build_parser()
    arguments = parser.parse_args(forwarded)
    try:
        _to_the_interpreter_the_target_names(parser, arguments)
    except launch.LaunchMisuse as misuse:
        # A word spelled like an interpreter that names none this client can run
        # in. Nothing was handed over and no program started, so it is the
        # invocation's mistake, like every other refusal before the hand-off.
        stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    return _run(arguments, stdout, stderr)


def _to_the_interpreter_the_target_names(
    parser: argparse.ArgumentParser, arguments: argparse.Namespace
) -> None:
    """Hand the whole command to the interpreter a target names, if it names another.

    `interpreter.py` says why. A target that names no interpreter is left
    alone; one that names the interpreter already running has the word taken
    off and goes on here; one that names another does not come back — this
    process becomes that interpreter running this same command.

    The command line handed over is respelled from what the parser READ, never
    cut out of what was typed: where the target begins in the raw words depends
    on how options and `--` were interleaved, and a rule about that written a
    second time here would be a second parser. Every option the verb's own
    parser declares is carried by walking that parser, so an option added to it
    later cannot be the one this forgot.
    """
    if os.environ.pop(interpreter.CHOSEN_VARIABLE, None):
        # This `sayfirst instrument` is the one a hand-off ran inside the
        # interpreter it chose: the target has been resolved once already and
        # runs here, in this process, without being read a second time. Reading
        # it again would exec away from the interpreter just chosen (a target
        # whose shebang names another) or loop forever (an interpreter that
        # resolves to a shim whose path never equals this one). Removed as it is
        # read, so a program that itself runs `sayfirst instrument` starts clean.
        return
    chosen = interpreter.selection(arguments.target)
    if chosen is None:
        return
    executable, program = chosen
    if interpreter.is_this_one(executable):
        # The interpreter the target names is the one already running: the word
        # (or nothing, for an executable whose shebang names this Python) is
        # taken off and the program runs here, exactly as it would have.
        arguments.target = program
        return
    interpreter.hand_the_command_to(
        executable,
        ["instrument", arguments.verb, *_respelled(parser, arguments), "--", *program],
        follow_children=getattr(arguments, "follow_children", False),
    )


def _respelled(parser: argparse.ArgumentParser, arguments: argparse.Namespace) -> list[str]:
    """Every option of this verb, as the words that would be read back as the same values."""
    verbs = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    words: list[str] = []
    for action in verbs.choices[arguments.verb]._actions:
        if not action.option_strings or isinstance(action, argparse._HelpAction):
            continue
        value = getattr(arguments, action.dest)
        option = action.option_strings[-1]
        if isinstance(value, bool):
            words.extend([option] if value else [])
        elif isinstance(value, list):
            for item in value:
                words.extend([option, str(item)])
        elif value is not None:
            words.extend([option, str(value)])
    return words


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
            packs.append(designation.read(named))
        except manifest.PackInvalid as invalid:
            # The designation as it was TYPED, not as it was resolved: with more than
            # one `--pack` the sentence alone does not say which one to fix, and
            # a resolved path is not what the reader has in their shell history.
            stderr.write(f"{named}: {invalid}\n")
            return exit_codes.EXIT_MISUSE
    try:
        address = reads.address_of(arguments)
        profile = SocketProfile(
            address.path,
            mode=arguments.mode,
            daemon_user=arguments.daemon_user,
            scope=arguments.scope,
        )
    except ProfileMisuse as invalid:
        stderr.write(f"{invalid}\n")
        return exit_codes.EXIT_MISUSE
    _say_an_empty_default(address, stderr)
    try:
        return launch.run(
            packs,
            profile,
            arguments.target,
            principal=arguments.principal,
            follow_children=getattr(arguments, "follow_children", False),
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
        # later, inside the program, is the program's and is handled below.
        return _write_problem(failure, stderr)
    except BoundaryError as outcome:
        # An outcome the boundary raised into the program, which did not handle
        # it. It ends the way the interpreter ends any program on an exception —
        # its traceback, through the program's own hook — and then with the
        # status this client publishes for that outcome. The interpreter's own
        # status for an uncaught exception is 1, this client's « deny », so a
        # shell could not tell a denial from a control plane that could not be
        # asked (article 1). A program that handles the outcome, or raises
        # something of its own from it, owns its ending and is not read here.
        sys.excepthook(type(outcome), outcome, outcome.__traceback__)
        code = ending_for(outcome)
        return exit_codes.EXIT_COULD_NOT_ASK if code is None else code


#: The status for each outcome the boundary can raise into a program, the same
#: numbers `ask` returns for the same answers.
_ENDINGS: Final[tuple[tuple[type[BoundaryError], int], ...]] = (
    (Denied, exit_codes.EXIT_DENY),
    (Suspended, exit_codes.EXIT_SUSPEND),
    (AskRefused, exit_codes.EXIT_REFUSED),
    (CouldNotAsk, exit_codes.EXIT_COULD_NOT_ASK),
)


def ending_for(outcome: BaseException) -> int | None:
    """The published status for a boundary outcome, or `None` for anything else."""
    for kind, code in _ENDINGS:
        if isinstance(outcome, kind):
            return code
    return None


def _say_an_empty_default(address: ProfileAddress, stderr: TextIO) -> None:
    """Name an address nobody typed when nothing is there, before the program starts.

    The connection is arranged when the program's first named effect asks, so a
    daemon that is not running is found out inside the program, as the
    boundary's own exception, which names no path. With `--socket` the reader
    typed the path; with the default they never saw it, and « could not ask »
    at a name nobody showed them is a failure they cannot act on (article 2).

    It changes nothing about what runs. A program that asks nothing still runs
    to its own ending, an effect a pack names still fails closed when it is
    reached, and a daemon that starts in between is simply asked — this is one
    line on the error stream, written only when it is true at the moment it is
    written, and it is the launcher's to write because the program has not
    started yet (`launch.py` draws that line).
    """
    if address.defaulted and not Path(address.path).exists():
        stderr.write(
            f"{address.looked_at()}\n"
            f"nothing is there now, so an effect these packs name will fail closed; "
            f"`sayfirst-daemon up --quickstart` starts a control plane at that address\n"
        )


def _write_problem(failure: SocketClientProblem, stderr: TextIO) -> int:
    """A non-answer, said as the reads say it, with the code the reads use."""
    result = reads.connection_problem(failure)
    could_not_ask = not isinstance(result, Refused)
    render.write_problem(
        result.problem.to_document(CONTRACT_GENERATION), stderr, could_not_ask=could_not_ask
    )
    return exit_codes.EXIT_COULD_NOT_ASK if could_not_ask else exit_codes.EXIT_REFUSED
