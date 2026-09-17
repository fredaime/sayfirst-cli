# SPDX-License-Identifier: Apache-2.0
"""`sayfirst instrument verify`: run the proof harness, and read its findings.

This is the command around `harness.py`. It reads the packs the way `run` does,
so a pack that will not read is the misuse it is before anything is spawned;
writes what it was asked into a configuration the harness reads; runs the
harness in a process of its own, because the hook that stops an ungoverned
effect can never be removed from an interpreter; and turns the report into
lines and into an exit code.

**The exit code is this command's and not the program's.** `run` passes the
governed program's ending through untouched, which is right for a launcher and
wrong for a proof: here the question is whether every named effect was decided,
so the program's own ending is reported as a fact (`target exit`) and the code a
shell sees comes from the verdicts. Zero means every point of every pack was
`governed` and no event on any of them went unjudged. `not-exercised` is never
zero — a path a run did not walk is not a path proven safe, and a verifier that
reported it green would be the false all-clear article 2 forbids. Neither is an
`unjudged` count, for the same reason read one step earlier: the harness
publishes, per point, how many events it could not judge at all, and a run
holding one of those has not finished proving anything about that point,
whatever the point's verdict says about the events it did judge.

**Where the program's own output goes, and why it is not stdout.** The verified
program keeps both its streams, and both of them arrive on THIS command's error
stream. It is the diagnostic stream for a verification run: the answer to
`verify` is the report, so `--json` has to be able to write an envelope a
machine reads, and a rule that moved the program's output depending on the
rendering asked for would be worse than a rule that is the same in both.

**`--json` answers in the envelope, and on a stream the program cannot reach.**
The verified program keeps both its streams and both arrive on this command's
error stream, which is right — the answer to `verify` is the report. It also
means a program can print `{"problem": …}` there, and this repository's own
tests parse an envelope from the first `{` they find. So the envelope goes to
stdout on every path, findings or none: on a no-answer path nothing else is
written to stdout, and on a reported path the envelope is the answer. The exit
code is the same either way — the rendering is not the verdict.

**How a no-answer path is told from the program's ending.** The harness writes
a file of its own saying which of its endings happened, and this command reads
that rather than the process's exit status. The status is the TARGET's: the
program runs inside the harness's interpreter, so `os._exit(64)` in the program
ends the harness with 64 — and 64 was read here as « the invocation was refused
before it began », a sentence about a program that had in fact run. One number
and two facts; `harness._write_outcome` carries the second, and says what the
channel is honest against.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, NamedTuple, TextIO

from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.problems import (
    Problem,
    ProblemCode,
    classes_by_code,
    problem_retryable,
)
from sayfirst_contract.transport.socket_client import (
    PER_USER,
    SYSTEM,
    ProfileMisuse,
    SocketProfile,
)

from .. import exit_codes, reads, render
from . import harness, manifest

#: The module the harness is run as. Named here so that the one place a second
#: interpreter is started names what it starts, and so a test can point it at
#: something that produces no report.
HARNESS_MODULE: Final[str] = "sayfirst_cli.instrument.harness"

#: What the configuration and the findings are called inside the directory this
#: command makes and removes. Neither outlives the run: a verification leaves
#: nothing on the machine it ran on.
CONFIGURATION_FILE: Final[str] = "verification-configuration"
REPORT_FILE: Final[str] = "verification-report"

#: Where the harness says which of ITS OWN endings happened, so this command
#: never has to read the target's exit status for it.
OUTCOME_FILE: Final[str] = "verification-outcome"

#: How long the harness may take, program included. A bound rather than none,
#: so a target that never ends is a verification that could not conclude rather
#: than a command that hangs for ever.
HARNESS_TIMEOUT: Final[float] = 900.0

#: What is said when a run concluded nothing, one sentence per reason. Each is
#: the prose a person reads and the `message` of the problem a machine reads,
#: so the two renderings cannot drift into saying different things.
NO_OUTCOME: Final[str] = (
    "no findings: the verification did not run to a conclusion, so nothing about this "
    "program is claimed either way (article 2)"
)
NOT_BEGUN: Final[str] = (
    "no findings: the verification was refused before it began, and the harness said "
    "why on this stream"
)
CHAIN_UNREADABLE_BEFORE_MESSAGE: Final[str] = (
    "no findings: the chain could not be read before the program started, so nothing was "
    "ever watched and nothing about this program is claimed"
)
CHAIN_UNREADABLE_DURING_MESSAGE: Final[str] = (
    "no findings: the chain could not be read while the program ran, so the effect was "
    "aborted on an unknown and nothing about this program is claimed"
)
UNREADABLE_FINDINGS: Final[str] = "the findings are not a report this client reads"

#: The sentence each of the harness's own endings is said with. Five endings and
#: five sentences, because « the chain could not be read » and « the gate never
#: opened » are different facts about different things and were one
#: `answer_unreadable` carrying one sentence between them — the cause surviving
#: only as prose the harness wrote on the error stream, which a machine reader
#: of the envelope never saw.
_SAID: Final[dict[str, str]] = {
    harness.INVOCATION_REFUSED: NOT_BEGUN,
    harness.CHAIN_UNREADABLE_BEFORE: CHAIN_UNREADABLE_BEFORE_MESSAGE,
    harness.CHAIN_UNREADABLE_DURING: CHAIN_UNREADABLE_DURING_MESSAGE,
    harness.GATE_NEVER_OPENED: harness.NEVER_STARTED,
    harness.REPORTED: UNREADABLE_FINDINGS,
}

#: The code an ending answers with when THIS CLIENT is the one that knows what
#: happened: an invocation it refused, a gate it never saw open, findings it
#: cannot read. Three rows and not five — the two chain endings are a read the
#: contract classified, and their code travels in the outcome file rather than
#: being minted here. A client that re-minted one would be publishing its own
#: classification of a problem the control plane already named, which is
#: article 1's rule about deriving an answer nobody gave, applied to a problem;
#: the measured cost of doing it was `unreachable` for a daemon that was
#: reached, answered, and spoke a generation this client does not read.
_NO_ANSWER: Final[dict[str, ProblemCode]] = {
    harness.INVOCATION_REFUSED: ProblemCode.REQUEST_MALFORMED,
    harness.GATE_NEVER_OPENED: ProblemCode.ANSWER_UNREADABLE,
    harness.REPORTED: ProblemCode.ANSWER_UNREADABLE,
}

#: What an ending with no code of its own and no row above answers with: the two
#: chain endings, when the outcome file carried no code the registry knows. « A
#: chain read did not answer and this client cannot say how it was classified »
#: is an answer it could not fully read, and it says that rather than guessing
#: at the transport's word for it.
UNCLASSIFIED: Final[ProblemCode] = ProblemCode.ANSWER_UNREADABLE


class Ending(NamedTuple):
    """What the harness said about its own ending, as this command reads it back.

    `code` is the transport's own classification of the chain read that did not
    answer, present only where there was one and the registry carries it.
    """

    reason: str
    detail: str
    code: ProblemCode | None


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The options this verb reads, declared beside the code that reads them."""
    parser.add_argument(
        "--pack",
        action="append",
        required=True,
        metavar="DIR",
        help="a pack directory; repeat the option for each pack",
    )
    parser.add_argument("--scope", required=True, help="the scope the questions are asked in")
    parser.add_argument("--socket", required=True, help="the path of the daemon's socket")
    parser.add_argument("--mode", choices=(PER_USER, SYSTEM), default=PER_USER)
    parser.add_argument(
        "--daemon-user",
        default=None,
        help="the account the daemon runs as; a system profile names it",
    )
    parser.add_argument(
        "--principal",
        default=None,
        metavar="REF",
        help="the principal reference to hold grants against; this account by default",
    )
    parser.add_argument(
        "--ungoverned",
        action="store_true",
        help="run the program with nothing in front of it; the chain alone answers",
    )
    parser.add_argument("--json", action="store_true", help="write the envelope instead of prose")
    parser.add_argument(
        "target",
        nargs="*",
        metavar="TARGET",
        help="after `--`: either -m MODULE [args] or SCRIPT [args]",
    )


def run(arguments: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    """Prove the program, and answer with the code the verdicts imply."""
    for named in arguments.pack:
        try:
            # Read and thrown away. The harness reads every pack again, because
            # it shares no state with this process; reading them here is what
            # makes a pack that will not read the misuse it is, rather than a
            # verification that could not be obtained for a reason the caller
            # would have to go and guess at.
            manifest.read_pack(Path(named))
        except manifest.PackInvalid as invalid:
            # The path as it was TYPED, for the reason `commands.py` gives.
            stderr.write(f"{named}: {invalid}\n")
            return exit_codes.EXIT_MISUSE
    try:
        SocketProfile(
            arguments.socket,
            mode=arguments.mode,
            daemon_user=arguments.daemon_user,
            scope=arguments.scope,
        )
    except ProfileMisuse as invalid:
        # Built and thrown away: the harness builds its own from the same
        # members, and a profile that cannot say what it must verify is a
        # mistake worth reporting before a second interpreter is started.
        stderr.write(f"{invalid}\n")
        return exit_codes.EXIT_MISUSE
    with tempfile.TemporaryDirectory(prefix="sayfirst-verify-") as directory:
        report = Path(directory) / REPORT_FILE
        outcome_file = Path(directory) / OUTCOME_FILE
        configuration = Path(directory) / CONFIGURATION_FILE
        configuration.write_text(
            json.dumps(
                {
                    "packs": list(arguments.pack),
                    "socket": arguments.socket,
                    "mode": arguments.mode,
                    "daemon_user": arguments.daemon_user,
                    "scope": arguments.scope,
                    "principal": arguments.principal,
                    "governed": not arguments.ungoverned,
                    "report": str(report),
                    harness.OUTCOME_FILE_MEMBER: str(outcome_file),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _harness_output(_harness(configuration, list(arguments.target)), stderr)
        document = _findings(report)
        if document is None:
            return _no_answer(outcome_file, arguments, stdout, stderr)
        return _rendered(document, arguments, stdout, stderr)


def _harness_output(finished: subprocess.CompletedProcess[str], stderr: TextIO) -> None:
    """Both of the program's streams, on the diagnostic stream, before the report:
    what it printed comes before what was concluded about it."""
    for written in (finished.stdout, finished.stderr):
        if written:
            stderr.write(written)


def _no_answer(
    outcome_file: Path, arguments: argparse.Namespace, stdout: TextIO, stderr: TextIO
) -> int:
    """A run that wrote no findings this command reads, answered from the harness's
    own account of how it ended rather than from the number a shell would see.

    The number is the TARGET's — the program runs inside the harness's
    interpreter — so a program calling `os._exit(64)` used to choose « refused
    before it began » for a verification that had in fact run. Only
    `INVOCATION_REFUSED` is the invocation's mistake, and only it answers 64,
    which is the code `instrument run` gives the very same mistake; `_EXIT_FOR`
    below says what the other endings answer, and why only one of them is not 4.
    """
    said = _outcome(outcome_file)
    if said is None:
        # The harness wrote neither findings nor an outcome: it did not reach
        # its own first statement, the interpreter never started, or the host
        # killed it. Not a refused invocation and not a conclusion.
        return _answer(
            ProblemCode.ANSWER_UNREADABLE,
            NO_OUTCOME,
            arguments,
            stdout,
            stderr,
            exit_codes.EXIT_COULD_NOT_ASK,
        )
    message = _SAID.get(said.reason, NO_OUTCOME)
    return _answer(
        # The transport's own code wherever the harness carried one, which is
        # both chain endings; the table only for the endings this client is the
        # one that knows about. The sentence is this command's either way — it
        # says which of the harness's endings happened, which no problem code
        # can say — and the detail behind it is the transport's own message.
        said.code if said.code is not None else _NO_ANSWER.get(said.reason, UNCLASSIFIED),
        f"{message}: {said.detail}" if said.detail else message,
        arguments,
        stdout,
        stderr,
        _EXIT_FOR.get(said.reason, exit_codes.EXIT_COULD_NOT_ASK),
    )


#: The code a shell reads for the two endings that are not « the verification
#: could not be obtained ». An invocation this client refused is the 64
#: `instrument run` gives the same mistake; findings that exist and will not
#: read are the 7 `_unreadable` answers for the very same sentence, and the one
#: `docs/PACKS.md` states — with the outcome file the client now KNOWS the
#: findings exist, which is what 7 is for. Every other ending is 4.
_EXIT_FOR: Final[dict[str, int]] = {
    harness.INVOCATION_REFUSED: exit_codes.EXIT_MISUSE,
    harness.REPORTED: exit_codes.EXIT_COULD_NOT_CHECK,
}


def _outcome(path: Path) -> Ending | None:
    """Which of its own endings the harness said happened, its detail, and its code.

    `None` for a file that is absent, will not read, or names an ending this
    command does not know — all of which are « the harness said nothing this
    command can use », which is what an absent file already means. A word
    outside the closed vocabulary is not guessed at.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(document, Mapping):
        return None
    named = document.get("outcome")
    detail = document.get("detail")
    if named not in harness.OUTCOMES or not isinstance(named, str):
        return None
    return Ending(
        named, detail if isinstance(detail, str) else "", _carried(document.get("problem_code"))
    )


def _carried(value: object) -> ProblemCode | None:
    """The transport's own code for this ending, where the registry carries it.

    A code the registry does not define is not promoted: an unknown is never
    read as more precise than the fallback (article 3), and a code this client
    cannot ask the registry about — for retryability, for its class — is one it
    must not publish as the classification of anything. Asked of the registry's
    own table rather than of a list kept here, so this file holds no codes but
    the three it mints for itself.
    """
    if not isinstance(value, str) or value not in classes_by_code():
        return None
    try:
        return ProblemCode(value)
    except ValueError:  # pragma: no cover - the registry and the enum agree
        return None


def _harness(configuration: Path, target: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run the harness in an interpreter of its own, and wait for it.

    `sys.executable` rather than a name looked up on the path: the harness is
    this distribution's own module, and the interpreter that can import it is
    the one running this command.

    A timeout is not a verdict. It comes back as a run that wrote no findings,
    which this command reports as a verification that did not conclude.
    """
    try:
        return subprocess.run(
            [sys.executable, "-m", HARNESS_MODULE, str(configuration), "--", *target],
            capture_output=True,
            text=True,
            timeout=HARNESS_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return subprocess.CompletedProcess(
            expired.cmd,
            returncode=exit_codes.EXIT_COULD_NOT_ASK,
            stdout=_text(expired.stdout),
            stderr=_text(expired.stderr)
            + f"the program had not ended after {HARNESS_TIMEOUT:g} seconds\n",
        )


def _text(value: object) -> str:
    """What a timeout kept of a stream, which may be bytes, text or nothing."""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value if isinstance(value, str) else ""


def _findings(report: Path) -> Mapping[str, object] | None:
    """The harness's report, or `None` when it wrote none this command can read.

    A report that is absent and a report that will not parse are the same fact
    here — there are no findings — and neither is turned into a verdict.
    """
    try:
        document = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(document, Mapping) or reads.too_deep(document):
        return None
    return document


def _rendered(
    document: Mapping[str, object],
    arguments: argparse.Namespace,
    out: TextIO,
    err: TextIO,
) -> int:
    """One line per point, then what was inspected and how the program ended.

    A point that carries an `unjudged` count gets a second line of its own
    rather than a word folded into its first. The verdict is about the events
    the run judged and stays exactly that; the count is the effect the run
    could NOT judge, and a reader has to be able to see both — which is why it
    is a line and not a suffix, and why `_exit_for` reads it rather than
    inferring it from the verdict.
    """
    points = document.get("points")
    if not isinstance(points, list):
        return _unreadable(arguments, out, err)
    verdicts: list[str] = []
    unjudged: list[int] = []
    lines: list[str] = []
    for point in points:
        if not isinstance(point, Mapping) or point.get("verdict") not in harness.VERDICTS:
            return _unreadable(arguments, out, err)
        counted = point.get(harness.UNJUDGED)
        # Required and required to be a count. A report of this distribution's
        # own harness always carries it; one that does not, or carries something
        # that is not a number of events, is findings this client cannot read —
        # which is answered as « could not check » and never as a verdict.
        if not isinstance(counted, int) or isinstance(counted, bool) or counted < 0:
            return _unreadable(arguments, out, err)
        verdicts.append(str(point["verdict"]))
        unjudged.append(counted)
        lines.append(
            f"{point['verdict']} {point.get('pack')} {point.get('module')}."
            f"{point.get('attribute')} {point.get('capability')} "
            f"events={point.get('events')}"
        )
        if counted:
            lines.append(
                f"{harness.UNJUDGED}: {counted} {point.get('pack')} {point.get('module')}."
                f"{point.get('attribute')} {point.get('capability')} — an effect named the "
                f"program's own start file after it had started, so this run could not "
                f"judge it and is not a pass (article 2)"
            )
    if arguments.json:
        render.write_json(
            render.envelope(CONTRACT_GENERATION, _verification(document), result=dict(document)),
            out,
        )
    else:
        for line in lines:
            out.write(f"{line}\n")
        inspected = document.get("inspected")
        named = " ".join(str(name) for name in inspected) if isinstance(inspected, list) else ""
        out.write(f"inspected: {named or render.NOT_STATED}\n")
        ending = document.get("target_exit")
        out.write(f"target exit: {'none' if ending is None else ending}\n")
    return _exit_for(verdicts, unjudged)


def _verification(document: Mapping[str, object]) -> Mapping[str, object]:
    """What the harness verified about the far end, or that it verified nothing."""
    verification = document.get("verification")
    if isinstance(verification, Mapping):
        return verification
    return render.verification_document(None, None, False)


def _unreadable(arguments: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    """A report whose findings this command cannot read is no proof at all.

    Never a verdict: the findings exist and this client could not read them,
    which is a check that did not conclude rather than a program found wanting.
    """
    return _answer(
        ProblemCode.ANSWER_UNREADABLE,
        UNREADABLE_FINDINGS,
        arguments,
        out,
        err,
        exit_codes.EXIT_COULD_NOT_CHECK,
    )


def _answer(
    code: ProblemCode,
    message: str,
    arguments: argparse.Namespace,
    out: TextIO,
    err: TextIO,
    exit_code: int,
) -> int:
    """A verification that concluded nothing, said the way this client says a problem.

    Under `--json` it is the envelope every other read writes for a problem, on
    **stdout** — the module docstring says why it is not the error stream here,
    and nothing else is written to stdout on any of these paths. In prose it is
    the sentence on the error stream, which is what a person reads beside the
    program's own output. The verification document says nothing was verified
    about a far end, because this process opened no connection: the harness's
    own verification is carried in a report, and there is no report.
    """
    document = Problem(code, message, problem_retryable(code), CONTRACT_GENERATION).to_document(
        CONTRACT_GENERATION
    )
    if arguments.json:
        render.write_json(
            render.envelope(
                CONTRACT_GENERATION,
                render.verification_document(None, None, False),
                problem=document,
            ),
            out,
        )
    else:
        err.write(f"{message}\n")
    return exit_code


def _exit_for(verdicts: Sequence[str], unjudged: Sequence[int] = ()) -> int:
    """Zero only when every point was governed and nothing went unjudged.

    A run with no point at all cannot conclude either: it would be the
    verification that inspected nothing and reported green, which article 9
    names as the thing the public gate has to fail on.

    An `unjudged` count answers « could not check » and takes precedence over
    zero, never over a finding: an effect this run could not judge leaves the
    proof incomplete, which is what 7 says, while 6 stays reserved for a
    finding this client actually made. A run cannot be a pass with one of
    these outstanding — that is the whole of the rule, whose measured shape
    before it existed was exit 0 and `governed` over an effect nobody decided.
    """
    if harness.UNGOVERNED in verdicts:
        return exit_codes.EXIT_CHECK_FAILED
    if not verdicts or harness.NOT_EXERCISED in verdicts or any(unjudged):
        return exit_codes.EXIT_COULD_NOT_CHECK
    return exit_codes.EXIT_ALLOW
