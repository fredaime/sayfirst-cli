# SPDX-License-Identifier: Apache-2.0
"""The proof harness: what the interpreter reported, against what the plane recorded.

Layer 3 of the instrumentation chain, and the one piece of it that trusts
nothing else in the chain. It watches the interpreter's own audit events and
reads the scope's evidence, and it holds no other source: no bookkeeping of the
engine's, no answer the boundary kept, nothing a pack said it had done. A proof
that trusts the thing it is proving is not a proof, which is why this file's
imports of the layers below it are the ones that RUN the program and read what
a pack declares — never the ones that would tell it what happened. (It names
the engine for one thing only: the exception class the engine raises out of the
program's own import, which is a refusal of the invocation and not a report of
anything that happened.)

**Why a process of its own.** The hook that stops an effect raises, and a hook
installed on this interpreter can never be removed. That irreversibility
disqualifies an audit hook as the engine — article 9 asks the primary mode to
be reversible — and is exactly what a proof harness wants. So the hook lives
and dies with this process, and the command that spawns it keeps none of it.

**What it concludes, in three words and no fourth.** `governed`: the effect
happened and a decision preceded it. `ungoverned`: the effect happened and no
decision preceded it. `not-exercised`: this run never walked the path. The
third is never a pass, and this file never turns it into one — it counts events
and writes them down; the command reads the report and decides the exit.

**One thing more is written down, and it is a COUNT rather than a fourth
word.** An event can arrive that this proof cannot judge at all: its argument
names one of the program's own start files after the program has begun, which
is the one shape `Watch` cannot tell from the hand-off's own reading of the
same file. Such an event is counted on the point it would have been judged
against and published as `unjudged`, beside a verdict that stays about the
events that WERE judged. It is not a verdict and not one of the three words:
every way of spelling it as one says something the run did not measure. What it
does is refuse the run a pass — `verify` cannot answer 0 while any count is
non-zero — which is the direction article 2 requires, and the direction this
rule failed in for as long as the same events were silently dropped.

**A fourth thing can happen, and it is not a verdict.** The chain may be
unreadable while the program runs. « No record exists » and « this client could
not read the chain » are different facts, and `exit_codes.py` keeps them apart:
a consultation in which not one read was answered ends the run with « could not
read » and no findings at all, never with `ungoverned`. The effect is still
aborted, because an effect whose governance could not be established is not one
this harness may let through — but nothing is concluded about the program.

**The wait, and why it is not a caller's to set.** Article 10 makes the chain
write asynchronous, so an effect's record may arrive after the effect was
allowed. The poll therefore has patience, and the patience is fixed here: a
verifier whose patience a caller could set to nothing would report `ungoverned`
for a daemon that was merely slow, which is a false finding rather than a
configurable one.

**Whose act was it.** `Watch` answers that question and nothing else, and it
exists because this harness runs inside the process it is watching: its own
chain reads, its own report write and the interpreter's own reading of the
program's file all raise the events a pack may have named. `Watch` says what
each rule excludes and why.

**Nothing here names a library.** The events it watches for are read off the
manifests the invocation designated — `tests/test_engine_is_agnostic.py` binds
this file for the same reason it binds the engine: a harness that knew one
library's event name would be the special case article 4 forbids, arriving
inside the one component whose whole job is to be impartial about what it
watches.
"""

from __future__ import annotations

import atexit
import json
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from sayfirst_contract.client import Answered, Result
from sayfirst_contract.problems import Problem, ProblemCode
from sayfirst_contract.transport.socket_client import (
    ProfileMisuse,
    SocketClientProblem,
    SocketProfile,
    VerifiedConnection,
    connect,
)

from .. import exit_codes, pages, reads, render
from . import engine, launch, manifest

#: An effect happened and a decision preceded it.
GOVERNED: Final[str] = "governed"

#: An effect happened and no decision preceded it.
UNGOVERNED: Final[str] = "ungoverned"

#: This run never walked the path. Never rendered as a pass (article 2).
NOT_EXERCISED: Final[str] = "not-exercised"

#: The closed vocabulary, so that a fourth word cannot be spelled by accident.
VERDICTS: Final[tuple[str, ...]] = (GOVERNED, UNGOVERNED, NOT_EXERCISED)

#: Whose act one event was. Three answers and not two, which is what the false
#: all-clear this rule was corrected for cost: an event whose argument names one of the
#: program's own start files, arriving after the gate opened, is neither the
#: hand-off's act nor one this proof can judge — and folding it into « not the
#: program's » hid an unjudged effect behind a judged one. These are NOT
#: verdicts and are deliberately not in `VERDICTS`: a verdict is about a point
#: across a whole run, and the vocabulary above stays three words wide.
THE_PROGRAMS: Final[str] = "the program's"
THE_HAND_OFFS: Final[str] = "the hand-off's"
NOT_JUDGED: Final[str] = "not judged"

#: What the report calls the count of events a point could not judge. A COUNT
#: and never a verdict — the run carries both, because « one effect on this
#: point was governed » and « another was not judged » are two facts and one
#: word cannot carry them.
UNJUDGED: Final[str] = "unjudged"

#: The kind of chain entry that records an effect, and the outcome that let it
#: happen. Both are the plane's own words, read and never translated.
EFFECT: Final[str] = "effect"
ALLOW: Final[str] = "allow"

#: How long one consultation waits for the record of an effect to appear.
#: Article 10 writes the chain asynchronously; see the module docstring for why
#: this is not an option.
CHAIN_WAIT: Final[float] = 2.0

#: How long between two poll cycles. Short enough that the wait above is spent
#: waiting rather than sleeping.
POLL_INTERVAL: Final[float] = 0.05

#: How many entries one read asks for, which is the daemon's own maximum.
PAGE_SIZE: Final[int] = 100

#: What separates this harness's own arguments from the program's.
SEPARATOR: Final[str] = "--"

#: What a run says when it never saw the program's own code begin. It is not a
#: verdict and it is not `not-exercised`: nothing was watched, so nothing about
#: the program was established — not even an absence.
NEVER_STARTED: Final[str] = (
    "the verifier never saw the program's own code start, so nothing about this program "
    "was watched and no verdict is reported: the interpreter ran it from a code object "
    "that carries no file this run resolved, which is what a module shipped as bytecode "
    "with no source beside it looks like"
)

#: The configuration member naming the file this harness says its own ending in.
OUTCOME_FILE_MEMBER: Final[str] = "outcome"

#: The findings were written; whatever else is wrong with them is the reader's
#: to say.
REPORTED: Final[str] = "reported"

#: The invocation was refused and the program never started.
INVOCATION_REFUSED: Final[str] = "invocation_refused"

#: The chain could not be read before the program started, so nothing was ever
#: watched.
CHAIN_UNREADABLE_BEFORE: Final[str] = "chain_unreadable_before"

#: The chain could not be read while the program ran, so an effect was aborted
#: on an unknown and nothing about the program is claimed.
CHAIN_UNREADABLE_DURING: Final[str] = "chain_unreadable_during"

#: The gate never opened: the interpreter never reported one of the program's
#: own code objects, so this proof never began watching.
GATE_NEVER_OPENED: Final[str] = "gate_never_opened"

#: The closed vocabulary of this harness's own endings, so a sixth cannot be
#: spelled by accident. They are NOT verdicts: a verdict is about a point across
#: a run, and these are about the run itself.
OUTCOMES: Final[tuple[str, ...]] = (
    REPORTED,
    INVOCATION_REFUSED,
    CHAIN_UNREADABLE_BEFORE,
    CHAIN_UNREADABLE_DURING,
    GATE_NEVER_OPENED,
)

#: The members the configuration must carry, and the shape each has to have.
#: Read through a table so that « declared as the wrong thing » and « not
#: declared at all » take one path to one refusal.
CONFIGURED: Final[tuple[str, ...]] = (
    "packs",
    "socket",
    "mode",
    "daemon_user",
    "scope",
    "principal",
    "governed",
    "report",
    OUTCOME_FILE_MEMBER,
)


class HarnessMisuse(ValueError):
    """This harness cannot run what it was asked to, and nothing was proven."""


class ChainUnreadable(RuntimeError):
    """An effect could not be verified, because the chain could not be read at all.

    Raised into the target, so the effect is aborted rather than let through on
    an unknown. It is deliberately NOT the same exception as an ungoverned
    effect, and it produces no finding: the problem is carried on the watch and
    the run ends with « could not read ». Publishing exit 6 — "a finding this
    client made" — for a plane that was never read would be exactly the
    collision between a finding and an unanswerable question that
    `exit_codes.py` exists to prevent (articles 1 and 2).
    """


@dataclass
class Watched:
    """One interposition point, and what this run observed about it."""

    pack: str
    point: manifest.Point
    events: int = 0
    refused: bool = False
    #: Events on this point that this run could not judge, because an argument
    #: named one of the program's own start files after the gate had opened —
    #: the one shape `Watch` cannot tell from the hand-off's own reading of the
    #: same file. Counted rather than dropped, and carried beside the verdict
    #: rather than folded into it: the command reads it and cannot answer 0.
    unjudged: int = 0

    @property
    def verdict(self) -> str:
        """The three words, in the one order that cannot flatter the run.

        An effect that was ever unproven is `ungoverned` whatever happened
        afterwards: a verdict is about the whole run, and a later decision does
        not retroactively decide an effect that already went unproven. A point
        no event reached is `not-exercised`, which is an absence and is said as
        one rather than counted with the sound ones (article 2).

        `unjudged` is not in here and must not be: it is a count of what this
        run could not establish, and every way of turning it into one of the
        three words says something the run did not measure — `ungoverned` would
        be a finding nobody made, `not-exercised` would deny the event that did
        arrive, and `governed` would be the false all-clear. So the verdict
        stays honest about the events that WERE judged, the count is published
        beside it, and the exit code is what refuses to call the run a pass
        (`verify._exit_for`).
        """
        if self.refused:
            return UNGOVERNED
        return NOT_EXERCISED if self.events == 0 else GOVERNED

    def to_document(self) -> dict[str, object]:
        return {
            "pack": self.pack,
            "module": self.point.module,
            "attribute": self.point.attribute,
            "capability": self.point.capability,
            "audit_event": self.point.audit_event,
            "verdict": self.verdict,
            "events": self.events,
            UNJUDGED: self.unjudged,
        }


class Watch:
    """Whose act an event was: the program's, or this harness's own.

    The question exists because the proof runs inside the process it is
    proving. Four rules, each excluding a different kind of act that is not the
    program's, and each one measurable rather than argued.

    **Armed only while the program runs.** Nothing is consulted before the
    launcher hands over or after the program is DONE. Before: the engine's load
    of a pack's execution module and the lookup of the target's own name.
    After: the report write and the traceback the interpreter is about to
    render. The hook is installed before the engine on purpose — an interpreter
    that could be asked to forget a hook would make the proof optional — so the
    arming, and not the installation, is what draws the line.

    « Done » is not « its main module returned ». A non-daemon thread the
    program started outlives that, and so does a handler it registered to run
    at exit; both are the program's own code, and the interpreter runs both
    after this process would otherwise have concluded.
    `_wait_for_the_program` is what makes this paragraph true, and says what it
    cost to leave untrue.

    **Not before the program's own code begins.** Handing a program over means
    locating it, reading it, reading or writing its bytecode cache, and only
    then executing it; every one of those is the hand-off's act and the
    interpreter reports them all. So nothing is judged until the interpreter
    reports one of the program's OWN code objects — the launcher names every
    file whose execution is the program running, and the FIRST of them to
    execute opens the gate. For a package named to `-m` that is its
    `__init__`, not its `__main__`: the `__init__` is the program's own code
    and it runs first, and a gate that waited for the `__main__` left every
    effect the `__init__` made unjudged and unaborted — measured as exit 0 over
    a spawn no decision covered.

    The gate is also what makes the count exact rather than nearly exact: the
    import system opens a bytecode cache under a name it derives itself and
    then writes through a bare descriptor, and neither can be recognised by any
    path a launcher could have named in advance.

    Its failure mode is the safe one, which is why it is allowed to be the rule
    that matters. A target whose executed code object does not carry a file the
    lookup resolved — a module shipped as bytecode with no source beside it —
    leaves this gate shut, and a run whose gate never opened concludes nothing
    at all: it says so and answers « could not read », rather than reporting
    the absence it never established (`_prove` says where).

    **Not inside a consultation.** A consultation reads the chain, and those
    reads are themselves acts the interpreter reports. Per thread, so an event
    arriving on another thread is still the program's and is still judged.

    **Not the files the hand-off itself reads, while it is still reading
    them.** The program's own file, a package's `__main__`, and the bytecode
    cache the import system keeps for each — named by the launcher, which asks
    the import system where a cache lives rather than spelling it. The import
    system's derivation from a cache is the one clause that outlives the gate
    opening: it writes a cache by creating a file named after that cache plus a
    number of its own, and a number known to nobody in advance can only be
    matched by the derivation, whenever it fires.

    **And whose act it was is three answers, not two.** The trade this rule
    used to make was stated here, and stated too weakly: « what it excludes and
    should not is a program that opens one of its OWN start files or their
    caches; that shows up as an absence — `not-exercised` — and never as a
    pass, which is the direction this trade has to fail in. » That held only
    when EVERY event on the point was excluded. Mixed with one judged event, the
    excluded ones vanished behind it and the run answered `governed`, exit 0 —
    measured through the shipped command on two pairs of programs differing in
    one argument — one pair opening a store under the program's own path
    instead of an ordinary one, the other spawning the program's own file as
    the executable instead of an ordinary command — each second effect real,
    and covered by no decision. That is the false all-clear article 2 forbids,
    in the component whose whole value is catching it.

    So an argument that names one of the program's own start files or their
    caches, arriving AFTER the gate opened, is answered `NOT_JUDGED` rather
    than `THE_HAND_OFFS`: the hand-off has finished reading those files by
    then, and this proof cannot tell the program naming its own file from the
    import system finishing with it. The caller counts it on the point and the
    run cannot be a pass. Measured on the six ordinary forms — a script, a
    module and a package, each cold and warm — every exclusion of either clause
    fires before the gate opens, so the count is zero in all of them and this
    answer is reserved for the shape it was written for.

    This is the ONE place an event's arguments are read, and reading them
    decides only whose act it was. Which arguments identify an effect is the
    pack's declaration and the boundary's digest (article 11); a verifier with
    an opinion of its own about them would be a second policy.
    """

    def __init__(self) -> None:
        self.armed = False
        self.started = False
        self.excluded: frozenset[str] = frozenset()
        #: The problem of a consultation in which no read was answered. Carried
        #: here as well as raised, so a target that caught the exception cannot
        #: bury the fact that nothing was verified.
        self.unreadable: Problem | None = None
        #: Whether the gate EVER opened. `disarm` clears `started`, and the run
        #: has to be able to tell « this program walked no such path » from
        #: « this proof never began watching » afterwards.
        self.ever_started = False
        self._starts: frozenset[str] = frozenset()
        self._derived: frozenset[str] = frozenset()
        self._ours = threading.local()

    @property
    def judging(self) -> bool:
        """Whether an event now is one this run may conclude anything from."""
        return self.armed and self.started

    def arm(self, starts: tuple[str, ...], own: tuple[str, ...], caches: tuple[str, ...]) -> None:
        """The launcher is about to hand over.

        `starts` are the program's OWN files — every one whose execution is the
        program running rather than the hand-off preparing it; the first of them
        to execute opens the gate. `own` are the files the hand-off reads to get
        there, and `caches` are those of them the import system derives further
        names from. All three come from the launcher, which is the only place
        they are known: resolving them again here, on a different import path,
        would be a different question with a different answer.
        """
        self._starts = _the_paths(starts)
        self.excluded = _the_paths(own)
        self._derived = _the_paths(caches)
        self.started = False
        self.armed = True

    def opening(self, arguments: tuple[object, ...]) -> None:
        """Open the gate once the interpreter reports the program's code, and alone.

        The interpreter reports running a code object by handing a hook that
        code object and nothing besides. Other events carry one too, and one of
        them comes first: the import system marshals a freshly compiled module
        in order to write its bytecode cache. So « the code object, by itself »
        is what tells « this is being run » from « this is being written down ».
        Measured on the way to this line: keyed on the code object wherever it
        appeared, the gate opened on the cache write and two of the hand-off's
        own file events were judged as the program's.

        It is deliberately NOT keyed on the event's name. Every audit event
        this harness knows is read from a pack's manifest, and the interpreter's
        own name for running code is read from nobody's — a name spelled here
        would be this file holding a vocabulary of its own, which is the thing
        article 4 denies it. The shape is an interpreter detail, so it is
        measured rather than trusted: `tests/test_instrument_verify.py` counts
        the events a `-m` run produces, cold and warm, and a shape that stops
        being unique arrives there as a red test.
        """
        if not self.armed or self.started or not self._starts:
            return
        if len(arguments) == 1 and _the_code_of(arguments[0]) in self._starts:
            self.started = True
            self.ever_started = True

    def disarm(self) -> None:
        """The program is done. Nothing after this is the program's act."""
        self.armed = False
        self.started = False

    @contextmanager
    def ours(self) -> Iterator[None]:
        """This harness's own work, for the length of the block."""
        self._ours.busy = True
        try:
            yield
        finally:
            self._ours.busy = False

    def whose(self, arguments: tuple[object, ...]) -> str:
        """Whose act this event was: the program's, this process's own, or nobody's.

        The third answer is the one that cannot be folded into the second. Read
        in the order below, because the clauses are not alternatives: an
        argument the import system derived is the import system's whenever it
        appears, and only what is left over can be the program naming its own
        start file.
        """
        if not self.judging or getattr(self._ours, "busy", False):
            return THE_HAND_OFFS
        named = [name for name in map(_resolved_argument, arguments) if name is not None]
        if any(self._derived_from_a_cache(name) for name in named):
            # A cache the import system derives is never the program's act, so
            # it is not judged and not aborted; but the gate is open here, and
            # a write this proof did not judge is COUNTED, so the run can never
            # read as a pass over it (article 2). Every ordinary form writes its
            # caches before the gate opens, so this count is zero where it is
            # green today; a program naming its own cache path is the one case.
            return NOT_JUDGED
        if any(name in self.excluded for name in named):
            return NOT_JUDGED
        return THE_PROGRAMS

    def _derived_from_a_cache(self, named: str) -> bool:
        """Whether a name is one the import system derived from a cache it was given.

        It writes a bytecode cache by creating a file named after that cache
        plus a number of its own, and renaming it. The number is the import
        system's and is never known in advance, so only the derivation can
        match it — which is why the caches arrive separately from the rest, and
        why this is the clause that is true whenever it fires rather than only
        while the hand-off is still reading.
        """
        return any(named.startswith(f"{cache}.") for cache in self._derived)


def _the_paths(paths: tuple[str, ...]) -> frozenset[str]:
    """Those of these this process can resolve, as it will see them reported."""
    return frozenset(
        resolved for resolved in (_resolved(path) for path in paths) if resolved is not None
    )


def _resolved(path: str) -> str | None:
    """One path as this process will see it reported, or `None` if unusable."""
    try:
        return str(Path(path).resolve())
    except (OSError, ValueError, RuntimeError):
        return None


def _the_code_of(argument: object) -> str | None:
    """The file an argument was compiled from, if the argument is a code object.

    Read as its own question rather than through the path reader below, because
    the gate asks something narrower: not « does this event mention a file »
    but « is this event the interpreter executing the program's own code ». No
    event carries a code object for the program's file before that.
    """
    compiled = getattr(argument, "co_filename", None)
    return _resolved(compiled) if isinstance(compiled, str) else None


def _resolved_argument(argument: object) -> str | None:
    """The file an event's argument names, if it names one.

    An argument may be a path, the bytes of one, something that supplies one,
    or a code object carrying the file it was compiled from. Anything else —
    a mode, a flag, an open descriptor — names no file and is not one.
    """
    if isinstance(argument, str):
        named: str | None = argument
    elif isinstance(argument, bytes):
        try:
            named = argument.decode()
        except UnicodeDecodeError:
            return None
    elif isinstance(argument, os.PathLike):
        named = os.fspath(argument) if isinstance(os.fspath(argument), str) else None
    else:
        compiled = getattr(argument, "co_filename", None)
        named = compiled if isinstance(compiled, str) else None
    return None if named is None else _resolved(named)


@dataclass(frozen=True)
class Configuration:
    """What the command asked this harness to prove, read strictly."""

    packs: tuple[Path, ...]
    profile: SocketProfile
    principal: str | None
    governed: bool
    report: Path
    #: Where this harness says which of its own endings happened. Validated like
    #: `report`, because a run that said it nowhere would leave the command
    #: reading the target's exit status again (`_write_outcome` says what that
    #: cost).
    outcome: Path


@dataclass(frozen=True)
class Consultation:
    """What one consultation of the chain established, and what it could not.

    Three outcomes rather than two, which is article 2's rule about a status
    surface applied to a single read: a record was found, no record was found
    in a chain that WAS read, or the chain was not read at all. Only the second
    is a finding about the program.
    """

    matched: int | None
    read_something: bool
    problem: Problem | None


@dataclass
class Chain:
    """The scope's evidence, as far as this harness has consumed it.

    The cursor is the sequence of the last entry a consultation matched. A read
    starts after it, so one recorded effect cannot answer for two events: the
    second consultation never sees it again.
    """

    connection: VerifiedConnection
    scope: str
    cursor: int
    #: One consultation at a time, because an audit event can arrive on any
    #: thread and two of them sharing one HTTP connection would interleave two
    #: reads on one socket.
    lock: threading.Lock = field(default_factory=threading.Lock)


def _write_outcome(
    path: Path, outcome: str, detail: str, *, problem: Problem | None = None
) -> None:
    """Say which of this harness's own endings happened, where the target cannot.

    The command that spawned this process used to read the PROGRAM's exit
    status to tell « this invocation was refused » from « this run concluded
    nothing », and a program that calls `os._exit(64)` chose that reading for
    it. An exit status carries one number and there are two facts; this file
    carries the second.

    The channel is honest against the ordinary program rather than against a
    hostile one: a target running as this user could write or unlink the file
    itself if it went looking for it. What it cannot do is choose the reading by
    accident, which is the whole of the collision this closes — and a target
    that wrote a false outcome deliberately would be a target lying about a
    proof it also controls the events of.

    **The transport's own classification travels with it where there is one.**
    Two of these endings are a chain read that did not answer, and the read
    carried a `Problem` the contract classified. Writing its code here is what
    stops the command that reads this file from minting a classification of its
    own for a problem the control plane already named — which is the same rule
    as « never derive an answer the control plane did not give » (article 1),
    applied to a problem rather than to a decision.

    Written best-effort: a run that could not write it is a run the caller
    reports as one that concluded nothing, which is what an absent file already
    means. Failing here would replace a readable non-answer with a traceback.
    The vocabulary check is not best-effort and is not an `assert`: assertions
    are stripped under `-O`, which this process inherits from its environment,
    and a word outside `OUTCOMES` written there would be read back as nothing
    at all.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"{outcome!r} is not one of this harness's own endings: {OUTCOMES}")
    said: dict[str, object] = {"outcome": outcome, "detail": detail}
    if problem is not None:
        code = problem.code
        said["problem_code"] = code.value if isinstance(code, ProblemCode) else code.raw
    with suppress(OSError):
        path.write_text(json.dumps(said) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Prove one program, write the report, and leave the verdict to the caller.

    The exit code here is about this harness: zero once the report is written,
    whatever the report says. The command that spawned it reads the report and
    the outcome file, never this number and never the program's — because « the
    program ended », « the program was governed » and « this harness got as far
    as X » are three different facts and one number cannot carry them.
    """
    forwarded = list(sys.argv[1:] if argv is None else argv)
    try:
        configured, target = _asked(forwarded)
    except HarnessMisuse as misuse:
        # There is no configuration, so there is no path to say this on. The
        # caller reads the absence of the file as « the harness wrote nothing at
        # all », which is exactly what happened.
        sys.stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    try:
        packs = [manifest.read_pack(path) for path in configured.packs]
    except manifest.PackInvalid as misuse:
        _write_outcome(configured.outcome, INVOCATION_REFUSED, str(misuse))
        sys.stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    try:
        connection = connect(configured.profile)
    except SocketClientProblem as failure:
        # No question was ever put and no chain was ever read, so there is no
        # report to write: nothing was proven and nothing is claimed.
        _write_outcome(
            configured.outcome,
            CHAIN_UNREADABLE_BEFORE,
            failure.problem.message,
            problem=failure.problem,
        )
        sys.stderr.write(
            f"the chain could not be read, so nothing was verified: {failure.problem.message}\n"
        )
        return exit_codes.EXIT_COULD_NOT_ASK
    try:
        return _prove(configured, packs, target, connection)
    finally:
        connection.close()


def _prove(
    configured: Configuration,
    packs: Sequence[manifest.Pack],
    target: Sequence[str],
    connection: VerifiedConnection,
) -> int:
    """Read the chain's head, install the hook, hand the program over, report."""
    watched = [Watched(pack.name, point) for pack in packs for point in pack.points]
    by_event: dict[str, list[Watched]] = {}
    for item in watched:
        by_event.setdefault(item.point.audit_event, []).append(item)
    watch = Watch()
    chain = Chain(connection, configured.profile.scope, cursor=0)
    with watch.ours():
        head = _head_of_the_chain(chain)
    if isinstance(head, Problem):
        _write_outcome(configured.outcome, CHAIN_UNREADABLE_BEFORE, head.message, problem=head)
        sys.stderr.write(f"the chain could not be read, so nothing was verified: {head.message}\n")
        return exit_codes.EXIT_COULD_NOT_ASK
    chain.cursor = head - 1
    # Installed before the hand-off — and before the engine, so an interpreter
    # that could be asked to forget a hook cannot make the proof optional. What
    # draws the line between this harness's work and the program's is the
    # ARMING, which the launcher does at the last instant (`Watch` says why).
    sys.addaudithook(_consulting(chain, by_event, watch))
    ending: int | None = None
    refused_the_invocation = False
    try:
        ending = _run_the_target(configured, packs, target, watch)
    except HarnessMisuse as misuse:
        # Before the hand-off every failure is this invocation's and the program
        # has not started (`launch.py` draws that line): there is nothing to
        # report about a program that never ran, and findings written anyway
        # would say `not-exercised` about a path no program was there to walk.
        refused_the_invocation = True
        _write_outcome(configured.outcome, INVOCATION_REFUSED, str(misuse))
        sys.stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    except engine.EngineMisuse as misuse:
        # A point naming an attribute a module does not have, discovered inside
        # the program's own import — the one check that cannot be made before
        # the hand-off (`engine.py` says why). The pack is the invocation's and
        # the program is innocent: no question was ever put, so this is the same
        # refusal `instrument run` gives the same mistake, and the command that
        # spawned this reads it off the outcome rather than off a number.
        refused_the_invocation = True
        _write_outcome(configured.outcome, INVOCATION_REFUSED, str(misuse))
        sys.stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    except ChainUnreadable:
        # The hook aborted an effect it could not verify. It is answered after
        # the `finally`, from the watch rather than from here, so that a target
        # which caught the exception cannot bury it.
        pass
    finally:
        # The program is not done because its main module returned, so the
        # watch stays armed until it is — its own threads run out and its own
        # exit handlers run, under the watch. Only then does consultation stop,
        # and it stops before anything else this process does: the report write
        # and the traceback the interpreter is about to render.
        _wait_for_the_program(chain)
        watch.disarm()
        if not refused_the_invocation and watch.unreadable is None and watch.ever_started:
            with watch.ours():
                _write_report(configured, packs, watched, head, ending, connection)
    if watch.unreadable is not None:
        _write_outcome(
            configured.outcome,
            CHAIN_UNREADABLE_DURING,
            watch.unreadable.message,
            problem=watch.unreadable,
        )
        sys.stderr.write(
            f"the chain could not be read while the program ran, so nothing was verified: "
            f"{watch.unreadable.message}\n"
        )
        return exit_codes.EXIT_COULD_NOT_ASK
    if not watch.ever_started:
        # The one fact that separates « this program walked no such path » from
        # « this proof never began watching ». Without it both rendered as
        # `not-exercised`, byte for byte — so a run that watched nothing at all
        # read exactly like a run that established an absence, which is the
        # distinction the rest of this file is fastidious about (article 2).
        _write_outcome(configured.outcome, GATE_NEVER_OPENED, " ".join(target))
        sys.stderr.write(f"{NEVER_STARTED}\n")
        return exit_codes.EXIT_COULD_NOT_ASK
    # No detail: the only path that reads this one is a report that will not
    # parse, and the report lives in a directory the command removes before the
    # reader ever sees the sentence — a path nobody can open is worse than none.
    _write_outcome(configured.outcome, REPORTED, "")
    return exit_codes.EXIT_ALLOW


def _wait_for_the_program(chain: Chain) -> None:
    """Run out everything the program left to do, before anything is concluded.

    A main module returning is not a program ending. Two things outlive it and
    both are the program's own code: a non-daemon thread it started, and a
    handler it registered to run at exit. The interpreter runs both — threads
    first, then the exit handlers — after this process would otherwise have
    disarmed the watch and written its findings. Measured before this existed,
    each against a chain holding one record and a program that spawned once
    itself: a thread that spawned 0.6 s later, and a handler that spawned at
    exit, each answered **exit 0 and `governed`** while BOTH processes ran —
    the second with no decision behind it, unjudged, unaborted and unreported.
    That is the false all-clear article 2 forbids, and a worker thread is the
    ordinary shape of the runtimes this chain exists to instrument.

    So both are run here, in the interpreter's own order, while the watch is
    still armed. **The exit handlers are run by this function rather than left
    to the interpreter**, and the choice is not about ordering among handlers —
    registering this harness's own work first would indeed run it last. It is
    about what a handler needs while it runs: the chain connection, which
    `main` closes on its way out, and a thread the handler may itself start,
    which nothing after the interpreter's handlers would join. Leaving the
    normal path to shutdown would put a consultation after the connection it
    reads through was closed. Doing it here keeps the whole sequence in one
    place a reader can see, and `atexit` clears its own register as it runs, so
    the interpreter's later call finds nothing and no handler runs twice.

    A handler's own failure is the program's, and `atexit` reports it the way
    the interpreter would and carries on — including the abort this harness
    raises into an ungoverned one, which is why a handler that is stopped does
    not stop the report.

    Every other handler in the register runs too, a few levels down in the
    standard library's own imports among them. That is not a liberty: the
    interpreter would run every one of them moments later, and nothing this
    process has left to do — writing a file, closing a socket — is anything
    they could take away.

    Daemon threads are not joined, because the interpreter does not join them
    either — it ends them at shutdown — so waiting for one could wait for ever
    on a thread the program never meant to finish. Waiting is therefore exactly
    as long as the interpreter itself would wait, and no longer; a program that
    hangs a non-daemon thread hangs this run, which is bounded by the command's
    own timeout rather than pretended away here.

    Threads are enumerated in a loop, and joined again after the handlers,
    because each of those can start another.

    Then the lock, which a consultation holds while it polls: findings written
    out from under a consultation still in flight would be findings made
    without the answer they were waiting for.
    """
    _join_the_programs_threads()
    # Not guarded against an exception: `atexit` prints what a handler raised
    # and goes on to the next, exactly as the interpreter does, so there is
    # nothing here to catch that it has not already reported.
    atexit._run_exitfuncs()
    _join_the_programs_threads()
    with chain.lock:
        pass


def _join_the_programs_threads() -> None:
    """Join every thread the interpreter itself would wait for, and no other."""
    while True:
        left = [
            thread
            for thread in threading.enumerate()
            if thread is not threading.current_thread() and not thread.daemon and thread.is_alive()
        ]
        if not left:
            break
        for thread in left:
            thread.join()


def _run_the_target(
    configured: Configuration,
    packs: Sequence[manifest.Pack],
    target: Sequence[str],
    watch: Watch,
) -> int | None:
    """Hand the program over, in the mode the invocation asked for.

    With `governed`, exactly what the launcher does, boundary and engine
    included: the verifier then measures the shipped mode. Without it, the same
    hand-off with nothing in front of the program, which is how the chain alone
    is asked whether an effect was decided.

    Either way the launcher arms the watch at the last instant before the
    program starts, and tells it which files the interpreter reads to start it.

    `LaunchMisuse` is the invocation's mistake and not a verdict, so it ends
    this harness with no report rather than with an unproven `governed`.
    """
    try:
        if configured.governed:
            return launch.run(
                list(packs),
                configured.profile,
                list(target),
                principal=configured.principal,
                out=sys.stdout,
                err=sys.stderr,
                starting=watch.arm,
            )
        return launch.hand_over(list(target), err=sys.stderr, starting=watch.arm)
    except launch.LaunchMisuse as misuse:
        raise HarnessMisuse(str(misuse)) from misuse


def _head_of_the_chain(chain: Chain) -> int | Problem:
    """The sequence a record written by this run would take, or the problem that it is unknown.

    The chain is walked to its end once, before the program starts, so that a
    record already there cannot be mistaken for one this run produced. An empty
    chain answers 1, which is the sequence the first entry would be given.

    The `Problem` and not only its message, because the caller writes its code
    into the outcome file: a read the daemon answered in a generation this
    client does not speak was classified by the transport, and a command that
    was handed that classification and published another of its own would be
    deriving an answer nobody gave it (article 1).
    """
    from_sequence = 1
    highest = 0
    while True:
        # Bound as a default so the read is of THIS page and not of whatever
        # the walk moved on to: the callable outlives one turn of the loop.
        result = reads.read(lambda at=from_sequence: _one_page(chain, at))
        if not isinstance(result, Answered):
            return result.problem
        entries, _, next_from = result.value
        for entry in entries:
            sequence = entry["sequence"]
            if isinstance(sequence, int) and sequence > highest:
                highest = sequence
        if next_from is None:
            return highest + 1
        from_sequence = next_from


def _one_page(
    chain: Chain, from_sequence: int
) -> Result[tuple[list[Mapping[str, object]], Mapping[str, object], int | None]]:
    """Re-open the connection, verify the far end again, and read one page.

    Rule C4: the transport re-opens no address on a caller's behalf, and the
    daemon closes the connection after some answers. Re-verifying before every
    read keeps that explicit — it is cheap over a Unix socket — and it puts the
    re-open inside the reader, so a socket that went away mid-run is a
    transport problem this client classifies rather than an exception raised
    out of an audit hook.
    """
    chain.connection.reconnect()
    result = chain.connection.read_evidence(chain.scope, from_sequence, PAGE_SIZE)
    if not isinstance(result, Answered):
        return result
    return Answered(pages.members(result.value, from_sequence), result.contract_generation)


def _consulting(
    chain: Chain, by_event: Mapping[str, list[Watched]], watch: Watch
) -> Callable[[str, tuple[object, ...]], None]:
    """The audit hook: for an event a pack named, ask the chain and act on the answer.

    Every other event returns on a dictionary lookup, which is what a hook
    installed for the length of somebody's program has to cost.

    A point the chain cannot account for raises, and the raise is the whole
    mechanism: it aborts the effect inside the target rather than reporting
    afterwards that an ungoverned effect had already happened. A point whose
    chain could not be read raises too, and for the same reason — but with a
    different exception and no finding, because that is not the same fact.

    Whose act an event was is `Watch`'s question, asked first and answered
    there; this function judges only what is left — and COUNTS what is neither
    judged nor the hand-off's, which is the one thing it may not drop
    (`Watch.whose` says what that shape is and what dropping it cost).
    """

    def consult(event: str, arguments: tuple[object, ...]) -> None:
        if not watch.judging:
            # Either nothing has been handed over yet, or the hand-off is still
            # locating and reading the program. Both are the watch's question
            # and not this function's; the second is also where the gate opens.
            watch.opening(arguments)
            return
        points = by_event.get(event)
        if points is None:
            return
        whose = watch.whose(arguments)
        if whose == THE_HAND_OFFS:
            return
        if whose == NOT_JUDGED:
            # No chain read and no raise: nothing was established about this
            # event, and inventing either answer would be a verdict nobody
            # measured. It is counted on every point the event would have been
            # judged against, which is what makes the run not a pass.
            for item in points:
                item.unjudged += 1
            return
        with watch.ours():
            for item in points:
                _judge(chain, item, watch)

    return consult


def _judge(chain: Chain, item: Watched, watch: Watch) -> None:
    """One point, against one consultation of the chain."""
    consultation = _consulted(chain, item.point.capability)
    if consultation.matched is not None:
        item.events += 1
        return
    if not consultation.read_something:
        problem = consultation.problem
        watch.unreadable = problem
        raise ChainUnreadable(
            f"the chain could not be read, so this effect is not verified: "
            f"{item.point.capability} ({item.point.audit_event}): "
            f"{'no answer at all' if problem is None else problem.message}"
        )
    if consultation.problem is not None:
        # Some reads were answered and the last was not. The verdict below is
        # made of what WAS read, and the failure is said beside it rather than
        # folded into it: a reader has to be able to see that the chain went
        # away while this run was concluding.
        sys.stderr.write(
            f"the chain was read and then stopped answering: {consultation.problem.message}\n"
        )
    item.refused = True
    raise RuntimeError(f"{UNGOVERNED} effect: {item.point.capability} ({item.point.audit_event})")


def _consulted(chain: Chain, capability: str) -> Consultation:
    """Poll the chain for a record this effect has not already been answered by.

    Polled, because article 10 writes the chain asynchronously: the record of
    an effect the plane allowed may arrive after the effect was allowed to
    happen.

    Every read that was not answered is remembered, and so is whether ANY was.
    A consultation that read nothing at all across the whole patience has
    established nothing about the program — not even an absence — which is why
    that is a third outcome here and not a `False`.
    """
    deadline = time.monotonic() + CHAIN_WAIT
    read_something = False
    problem: Problem | None = None
    with chain.lock:
        while True:
            found, answered, failure = _matching(chain, capability)
            read_something = read_something or answered
            if failure is not None:
                problem = failure
            if found is not None:
                chain.cursor = found
                return Consultation(found, True, None)
            if time.monotonic() >= deadline:
                return Consultation(None, read_something, problem)
            time.sleep(POLL_INTERVAL)


def _matching(chain: Chain, capability: str) -> tuple[int | None, bool, Problem | None]:
    """One walk: the sequence matched, whether any page was answered, and the problem.

    Nothing is inferred from a read that was not answered — not here and not in
    the poll above, which is what carries « no read succeeded » out to the
    caller instead of letting it look like « no record exists ».
    """
    answered = False
    from_sequence = chain.cursor + 1
    while True:
        result = reads.read(lambda at=from_sequence: _one_page(chain, at))
        if not isinstance(result, Answered):
            return None, answered, result.problem
        answered = True
        entries, _, next_from = result.value
        for entry in entries:
            sequence = entry.get("sequence")
            body = entry.get("body")
            if (
                isinstance(sequence, int)
                and sequence > chain.cursor
                and entry.get("kind") == EFFECT
                and isinstance(body, Mapping)
                and body.get("capability") == capability
                and body.get("outcome") == ALLOW
            ):
                return sequence, True, None
        if next_from is None:
            return None, answered, None
        from_sequence = next_from


def _write_report(
    configured: Configuration,
    packs: Sequence[manifest.Pack],
    watched: Sequence[Watched],
    start_sequence: int,
    target_exit: int | None,
    connection: VerifiedConnection,
) -> None:
    """Write what this run observed, whatever ended it.

    Written from a `finally`, because the interesting run is the one the target
    did not survive: an effect the hook aborted kills the program, and a proof
    that lost its own findings to the failure it caused would prove nothing.

    `inspected` is read off the points that were actually watched for rather
    than off the command line. Article 9 asks the public gate to fail unless
    the verifier inspected every shipped pack, and a set copied from the
    invocation would satisfy that assertion without having watched anything.
    """
    inspected = sorted({item.pack for item in watched})
    document = {
        "packs": [pack.name for pack in packs],
        "inspected": inspected,
        "points": [item.to_document() for item in watched],
        "target_exit": target_exit,
        "start_sequence": start_sequence,
        "verification": render.verification_document(
            connection.server_credential.uid, connection.expected_uid, connection.verified
        ),
    }
    configured.report.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _asked(forwarded: Sequence[str]) -> tuple[Configuration, list[str]]:
    """The configuration and the program, or the misuse that there is neither."""
    argv = list(forwarded)
    if not argv:
        raise HarnessMisuse(
            f"this harness is run as `<configuration> {SEPARATOR} <target…>`, and was given nothing"
        )
    if SEPARATOR not in argv[1:]:
        raise HarnessMisuse(
            f"this harness was given no `{SEPARATOR}`: the program to prove follows it"
        )
    at = argv.index(SEPARATOR, 1)
    return _configured(Path(argv[0])), argv[at + 1 :]


def _configured(path: Path) -> Configuration:
    """Read the configuration, naming the member and the rule on every refusal."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as unreadable:
        raise HarnessMisuse(
            f"{path} does not read as a configuration: {unreadable}"
        ) from unreadable
    if not isinstance(document, Mapping):
        raise HarnessMisuse(f"{path} is not a configuration: it declares no members")
    declared = {member: None for member in CONFIGURED} | dict(document)
    packs = declared["packs"]
    if not isinstance(packs, list) or not packs or not all(isinstance(it, str) for it in packs):
        raise HarnessMisuse(
            f"packs is {packs!r}: a verification names the pack directories it watches for, "
            f"as a non-empty list of paths — one that watched for nothing would be the "
            f"vacuous proof article 9 forbids"
        )
    for member in ("socket", "scope", "mode"):
        if not isinstance(declared[member], str) or not declared[member]:
            raise HarnessMisuse(f"{member} is {declared[member]!r}: it names a non-empty string")
    for member in ("daemon_user", "principal"):
        if declared[member] is not None and not isinstance(declared[member], str):
            raise HarnessMisuse(f"{member} is {declared[member]!r}: it is a string or absent")
    if not isinstance(declared["governed"], bool):
        raise HarnessMisuse(
            f"governed is {declared['governed']!r}: it says whether the program is handed over "
            f"with the boundary in front of it, as true or false and never as an absence"
        )
    if not isinstance(declared["report"], str) or not declared["report"]:
        raise HarnessMisuse(
            f"report is {declared['report']!r}: it names the path this run's findings are "
            f"written to, and a run that wrote them nowhere would prove nothing"
        )
    if not isinstance(declared[OUTCOME_FILE_MEMBER], str) or not declared[OUTCOME_FILE_MEMBER]:
        raise HarnessMisuse(
            f"{OUTCOME_FILE_MEMBER} is {declared[OUTCOME_FILE_MEMBER]!r}: it names the path "
            f"this run says its own ending on, and a run that said it nowhere would leave "
            f"the command reading the target's exit status for it"
        )
    try:
        profile = SocketProfile(
            declared["socket"],
            mode=declared["mode"],
            daemon_user=declared["daemon_user"],
            scope=declared["scope"],
        )
    except ProfileMisuse as invalid:
        raise HarnessMisuse(str(invalid)) from invalid
    return Configuration(
        packs=tuple(Path(it) for it in packs),
        profile=profile,
        principal=declared["principal"],
        governed=declared["governed"],
        report=Path(declared["report"]),
        outcome=Path(declared[OUTCOME_FILE_MEMBER]),
    )


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    raise SystemExit(main())
