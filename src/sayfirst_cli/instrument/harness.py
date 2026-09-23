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

**The one rule every one of those three answers to.** A point is `governed`
only from evidence this run actually READ, actually found SOUND, and actually
tied to the effect it watched — and only over a run it watched WHOLE. It is
`ungoverned` only where the chain was read to its END and holds no record of
this run's, because that word is a finding this client made and a finding needs
the whole chain. Everything else — evidence the chain's own verification does
not report intact, a walk that stopped half way, a record this run cannot tell
from another execution's, an effect that reached the world along a path no point
interposes, a fork whose child's observations are in a memory this process
cannot read — is an INCOMPLETENESS, and an incompleteness is neither.

**So one thing more is written down, and it is a COUNT rather than a fourth
word.** Every incompleteness above is counted on the point it touches and
published as `unjudged`, with its reason beside it, next to a verdict that stays
about the observations that WERE judged. It is not a verdict and not one of the
three words: every way of spelling it as one says something the run did not
measure. What it does is refuse the run a pass — `verify` cannot answer 0 while
any count is non-zero — which is the direction article 2 requires, and the
direction this rule failed in for as long as each of those was silently dropped,
counted as a pass, or published as a finding nobody had the information to make.

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
import pwd
import sys
import threading
import time
import tomllib
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NamedTuple

from sayfirst_contract.client import Answered, Result
from sayfirst_contract.decisions import Outcome
from sayfirst_contract.evidence import ChainCondition
from sayfirst_contract.problems import Problem, ProblemCode, problem_class_of
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
#: happen. Both are the plane's own words, read and never translated — taken
#: from where they are published rather than spelled again here.
EFFECT: Final[str] = pages.EFFECT
ALLOW: Final[str] = Outcome.ALLOW.value

#: What a served verification says about a range a record may be taken from.
#: The contract publishes four conditions and exactly one of them is « the
#: writer verified this range »; the other three are a break, a declared gap
#: and « could not tell ». A record read out of any of those is evidence its own
#: writer declined to stand behind, and a conclusion drawn from it would be a
#: claim stronger than the evidence held (article 2).
INTACT: Final[str] = ChainCondition.intact.value

#: The member a point may declare naming the audit events by which an effect of
#: its kind reaches the world along a path the point does NOT interpose.
#: Declared by the pack, because a pack is the one place a library's vocabulary
#: may be written down (article 4) — and read here rather than through
#: `manifest.Point` for the reason `uninterposed_events` gives.
UNINTERPOSED: Final[str] = "uninterposed_events"

#: The member a point may declare naming, among its uninterposed events, the
#: ones its OWN interposed call raises on the way to the effect it was asked
#: for — the same act, reached through that call's implementation. Declared by
#: the pack for the same reason, and read the same way (`inner_events`).
INNER: Final[str] = "inner_events"

#: What the report calls the reasons behind a point's `unjudged` count. The
#: count is what refuses the run a pass; the reasons are what let a reader act
#: on it, and a count with no reason is a number nobody can do anything about.
INCOMPLETE: Final[str] = "incomplete"

#: Why one observation could not be judged. Five shapes, written out rather
#: than summarised, because « the evidence was damaged », « the walk stopped
#: half way », « the decision may be another execution's », « the effect took a
#: path nothing watches » and « the observation is in a child's memory » are
#: five different facts about five different things, and a reader who is told
#: only « 1 unjudged » cannot tell which of them happened.
A_START_FILE: Final[str] = (
    "an argument named one of the program's own start files after the program had started, "
    "which this proof cannot tell from the import system finishing with that same file"
)
EVIDENCE_NOT_INTACT: Final[str] = (
    "the record for this effect sits in a range the chain's own verification does not report "
    "intact, so it is evidence the writer of the chain declined to stand behind"
)
ANOTHER_EXECUTIONS_RUN: Final[str] = (
    "the record for this effect does not carry this run's correlation, so it may be a decision "
    "another execution of this principal obtained"
)
WALK_INTERRUPTED: Final[str] = (
    "the chain was read and the walk did not reach its end, so no record was found and no "
    "absence was established either"
)
PATH_NOT_INTERPOSED: Final[str] = (
    "an effect of a kind this pack names reached the world through an event no point of that "
    "pack interposes, so this run neither judged it nor stopped it — instrumentation can miss "
    "a call, and this is that limit counted rather than dropped"
)
THE_RUN_FORKED: Final[str] = (
    "this run forked, and what a child observed lives in a memory this report was not written "
    "from, so no point of it covers the whole run"
)

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


class NotJudged(RuntimeError):
    """An effect this run could not judge, aborted rather than let through.

    It is deliberately NOT the exception an ungoverned effect raises, and it
    carries no finding: `Watched.refused` stays false and the point's verdict
    stays about the events that WERE judged. What it leaves behind is a count
    and a reason, which is what refuses the run a pass without inventing a
    finding nobody made (article 2).

    It is a `RuntimeError` so that a program written to survive the abort of an
    ungoverned effect survives this one the same way: the two are one event
    from inside the program — an effect was stopped — and differ only in what
    this client may say about it afterwards.
    """


@dataclass
class Watched:
    """One interposition point, and what this run observed about it."""

    pack: str
    point: manifest.Point
    events: int = 0
    refused: bool = False
    #: Observations on this point that this run could not conclude anything
    #: from. Counted rather than dropped, and carried beside the verdict rather
    #: than folded into it: the command reads it and cannot answer 0.
    unjudged: int = 0
    #: Why, one sentence per distinct reason and each kept once. The count is
    #: what the command reads; these are what a person reads.
    reasons: list[str] = field(default_factory=list)

    def not_judged(self, reason: str) -> None:
        """Count one observation this run could not conclude anything from.

        Every way of turning one of these into a verdict says something the run
        did not measure, so none of them does: the count goes up, the reason is
        kept, and `verify._exit_for` is what refuses the pass.
        """
        self.unjudged += 1
        if reason not in self.reasons:
            self.reasons.append(reason)

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
            INCOMPLETE: list(self.reasons),
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
        #: Whether this run forked while the program was running. A fork copies
        #: this object, the chain's position and every `Watched`; what the child
        #: then observes changes ITS copies, in a memory the parent that writes
        #: the report cannot read. The parent can see that it happened, and
        #: that is what it says (`_forked` says what it costs not to).
        self.forked = False
        #: Whether THIS process is such a child. It shares the parent's report
        #: and outcome paths, and a child that wrote them would replace the
        #: parent's findings with its own view of a run the parent is still
        #: concluding.
        self.in_a_forked_child = False
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

    More than two outcomes, which is article 2's rule about a status surface
    applied to a single read. A record was found; or the chain was read to its
    END and holds no record of this run's, which is the one outcome that is a
    finding about the program; or the chain was not read at all; or it was read
    in part and the walk never reached the end, which establishes nothing; or a
    record was seen and could not be used, which establishes nothing either.
    """

    matched: int | None
    read_something: bool
    #: Whether any walk inside the patience reached the chain's end. Only then
    #: has « no record exists » been established: a walk that stopped half way
    #: has read the part it read and says nothing about the rest, and a finding
    #: made from it is a negative fact published on incomplete information.
    established_absence: bool
    problem: Problem | None
    #: A record this consultation saw and could not take, and why. Never a
    #: finding and never a pass: it is the third value.
    unusable: str | None
    #: Whether a record for this capability exists in the scope that another
    #: principal obtained. Said on the error stream, so a reader is not left
    #: wondering why an allow they can see in the chain answered for nothing.
    foreign: bool


@dataclass
class Chain:
    """The scope's evidence, and what this run has taken from it.

    **The floor never moves.** It is the position the chain had before the
    program started, and every read begins after it. What moves instead is
    `spent`: the sequences a consultation actually USED. A single moving cursor
    spent everything it stepped over as well, so a record matched out of
    decision order buried every earlier one behind it — and the effect an
    earlier record covered was then published as a finding against a decision
    sitting in the chain (`_matching` says what that cost).

    **Whom a record has to belong to.** A record supports an effect of this run
    only if the plane recorded it for the account this process runs as
    (article 6: identity is the operating system's, and the peer of the
    boundary's connection is this process). `one_execution` says whether the
    decisions this run looks for were taken BY this run: under the shipped,
    governed hand-off they were, so every record taken must also come from one
    connection — the one this run's own boundary holds. Under `--ungoverned`
    the program runs with nothing in front of it and the chain alone answers,
    so the records were written by another execution by construction and no
    connection may be required of them.
    """

    connection: VerifiedConnection
    scope: str
    #: The position the chain had before the program started. It never moves.
    floor: int
    #: One consultation at a time, because an audit event can arrive on any
    #: thread and two of them sharing one HTTP connection would interleave two
    #: reads on one socket.
    lock: threading.Lock = field(default_factory=threading.Lock)
    #: The sequences consultations have USED, so one recorded effect cannot
    #: answer for two events and a record nobody used stays reachable.
    spent: set[int] = field(default_factory=set)
    #: How the plane names the account this process runs as.
    principals: frozenset[str] = field(default_factory=lambda: _this_executions_principals())
    #: Whether this run's own boundary is what asked (see the class docstring).
    one_execution: bool = False
    #: The correlation this run's boundary stamped on every ask, or None under
    #: `--ungoverned` (no boundary asked). A record must carry it to be this
    #: run's. The shipped boundary holds one connection per grant, so a run
    #: spans several connections and a record's connection cannot stand for its
    #: run; this token is one value per run, known before the first record is
    #: read, so it checks the first record too.
    correlation: str | None = None


def _this_executions_principals() -> frozenset[str]:
    """How the plane names the account this process runs as, in every spelling.

    The daemon builds a principal from the peer credential of the connection and
    records it under the account's name, or under the uid where the directory
    could not name one. Both are computed here, so a record naming either is
    recognised and a record naming neither is somebody else's.

    A lookup that cannot be made leaves the uid, which is the one spelling no
    directory is needed for. The set is never empty: a run that could not say
    who it is must refuse every record rather than accept them all.
    """
    uid = os.geteuid()
    named = {str(uid)}
    # A uid with no account keeps the uid, which is the spelling no directory
    # is needed for; the set is never empty.
    with suppress(KeyError, OSError):
        named.add(pwd.getpwuid(uid).pw_name)
    return frozenset(named)


@dataclass(frozen=True)
class Walk:
    """One walk of the chain for one capability: what it found, and how far it got."""

    matched: int | None
    #: Whether any page was answered at all.
    answered: bool
    #: Whether the walk reached the chain's end, which is what an absence needs.
    whole: bool
    problem: Problem | None
    unusable: str | None
    foreign: bool


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
        # And its class, asked of the value: the plane refusing the read and
        # this client failing to read the answer are 3 and 4, and the same code
        # is minted on both sides of the wire, so the code cannot say which.
        said["problem_class"] = problem_class_of(problem)
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
        connection = connect(configured.profile, timeout=reads.READ_TIMEOUT)
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

    def say(outcome: str, detail: str, *, problem: Problem | None = None) -> None:
        """This run's own ending, written by the process that IS the run.

        A forked child reaching one of these lines is the program's copy of this
        harness and not a second verification: it holds the parent's paths, and
        writing them would replace the parent's findings with a child's view of
        a run the parent is still concluding.
        """
        if watch.in_a_forked_child:
            return
        _write_outcome(configured.outcome, outcome, detail, problem=problem)

    try:
        uninterposed = _the_paths_no_point_interposes(packs, watched)
        inner = _the_inner_events(packs)
    except manifest.PackInvalid as misuse:
        # A declaration this reader cannot read is the invocation's mistake and
        # not the program's: nothing has run and no question was ever put.
        say(INVOCATION_REFUSED, str(misuse))
        sys.stderr.write(f"{misuse}\n")
        return exit_codes.EXIT_MISUSE
    # One token for this run, generated here and handed to the boundary through
    # the launcher, so a record the plane stamped with it is one this run
    # produced. Only under the governed hand-off, where this run's own boundary
    # asks; under `--ungoverned` no boundary asks and the chain alone answers.
    correlation = f"sayfirst-verify:{uuid.uuid4()}" if configured.governed else None
    chain = Chain(
        connection,
        configured.profile.scope,
        floor=0,
        one_execution=configured.governed,
        correlation=correlation,
    )
    with watch.ours():
        head = _head_of_the_chain(chain)
    if isinstance(head, Problem):
        say(CHAIN_UNREADABLE_BEFORE, head.message, problem=head)
        sys.stderr.write(f"the chain could not be read, so nothing was verified: {head.message}\n")
        return exit_codes.EXIT_COULD_NOT_ASK
    chain.floor = head - 1
    # A fork copies everything this run concludes from, into a memory the
    # process that writes the report cannot read. Registered before the hook,
    # so that a program forking on its first line is already covered.
    os.register_at_fork(
        after_in_parent=lambda: _forked(watch, watched),
        after_in_child=lambda: _in_a_forked_child(watch),
    )
    # Installed before the hand-off — and before the engine, so an interpreter
    # that could be asked to forget a hook cannot make the proof optional. What
    # draws the line between this harness's work and the program's is the
    # ARMING, which the launcher does at the last instant (`Watch` says why).
    sys.addaudithook(_consulting(chain, by_event, uninterposed, watch, inner))
    ending: int | None = None
    refused_the_invocation = False
    try:
        ending = _run_the_target(configured, packs, target, watch, correlation)
    except HarnessMisuse as misuse:
        # Before the hand-off every failure is this invocation's and the program
        # has not started (`launch.py` draws that line): there is nothing to
        # report about a program that never ran, and findings written anyway
        # would say `not-exercised` about a path no program was there to walk.
        refused_the_invocation = True
        say(INVOCATION_REFUSED, str(misuse))
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
        say(INVOCATION_REFUSED, str(misuse))
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
        if (
            not refused_the_invocation
            and watch.unreadable is None
            and watch.ever_started
            and not watch.in_a_forked_child
        ):
            with watch.ours():
                _write_report(configured, packs, watched, head, ending, connection)
    if watch.unreadable is not None:
        say(
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
        say(GATE_NEVER_OPENED, " ".join(target))
        sys.stderr.write(f"{NEVER_STARTED}\n")
        return exit_codes.EXIT_COULD_NOT_CHECK
    # No detail: the only path that reads this one is a report that will not
    # parse, and the report lives in a directory the command removes before the
    # reader ever sees the sentence — a path nobody can open is worse than none.
    say(REPORTED, "")
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

    **And first of all, the callbacks the interpreter runs before it joins
    anything.** That order is not a detail: a worker parked on an empty queue
    is woken by a shutdown callback and by nothing else, and joining it before
    the callback ran waits for a thread nobody has told to stop.
    `_wake_what_the_interpreter_would_wake` says what that cost.
    """
    _wake_what_the_interpreter_would_wake()
    _join_the_programs_threads()
    # Not guarded against an exception: `atexit` prints what a handler raised
    # and goes on to the next, exactly as the interpreter does, so there is
    # nothing here to catch that it has not already reported.
    atexit._run_exitfuncs()
    # Again, because a handler can have started a pool of its own, exactly as
    # the second join exists because a handler can have started a thread.
    _wake_what_the_interpreter_would_wake()
    _join_the_programs_threads()
    with chain.lock:
        pass


def _wake_what_the_interpreter_would_wake() -> None:
    """Run the shutdown callbacks the interpreter runs BEFORE it joins a thread.

    `threading` keeps a register of its own, separate from `atexit`, for the
    work that has to happen while the threads are still there to be told. The
    interpreter runs it first, then joins every non-daemon thread, and only
    then reaches the `atexit` handlers. A pool of workers uses exactly that
    order: its workers are parked on a queue that only its own callback puts a
    sentinel on, and its threads are not daemons.

    This function ran nowhere, and the join came first. Measured on a program
    whose library held a pool at module scope, finished its one task and
    returned normally: the program printed its last line, the join waited on a
    worker nobody had woken, and the verification sat there until the command's
    own fifteen-minute bound — reported afterwards as a run that concluded
    nothing, about a program that had in fact finished. A library holding a
    pool is the ordinary shape of the runtimes this chain exists to instrument.

    Read off `threading` rather than kept here, and tolerated absent: this is
    the interpreter's own register, and a build that does not publish it leaves
    a run exactly where it was before — which is a bound rather than a hang,
    because the command has one.

    A callback's own failure is not this harness's to repair. It is suppressed
    and the rest are run, because the interpreter would reach every one of them
    moments later and this process has a report to write either way.
    """
    callbacks = getattr(threading, "_threading_atexits", None)
    if not callbacks:
        return
    for call in list(callbacks):
        with suppress(Exception):
            call()


def _forked(watch: Watch, watched: Sequence[Watched]) -> None:
    """The parent's side of a fork: say that this report does not cover the run.

    A fork copies the hook, the chain's position and every `Watched` into a
    memory the parent cannot read. The child goes on being watched — it aborts
    an effect no record covers, exactly as the parent would — and then its
    findings end with it. Measured before this existed: a worker that met an
    ungoverned effect, caught the abort and exited 0 was joined by a parent
    that reported `governed`, exit 0, over a run in which an effect had been
    refused.

    Collecting a child's findings is not something this side of a fork can do.
    Saying that they are missing is, and that is the whole of this function: one
    count on every point, once per run, because « this report does not cover the
    child » is one fact about the run and not one per fork.
    """
    if not watch.judging or watch.in_a_forked_child or watch.forked:
        return
    watch.forked = True
    for item in watched:
        item.not_judged(THE_RUN_FORKED)
    sys.stderr.write(f"{NOT_JUDGED}: {THE_RUN_FORKED}\n")


def _in_a_forked_child(watch: Watch) -> None:
    """The child's side: this process is a copy and writes none of the run's files."""
    watch.in_a_forked_child = True


def uninterposed_events(pack: manifest.Pack) -> dict[int, tuple[str, ...]]:
    """The paths a pack declares that it does NOT interpose, by the point declaring them.

    A pack is the one place a library's vocabulary may be written down (article
    4), so the events by which an effect of a pack's kind can reach the world
    are the pack's to name. A point that names none claims none, and a run over
    such a pack accounts for exactly what it did before.

    **Read from the manifest here, rather than carried on `manifest.Point`.**
    The two readers answer two questions. `manifest` reads what the ENGINE
    installs, and this member declares precisely what no engine installs: a path
    the pack deliberately leaves alone. Handing it to the engine's own point
    would give the engine a member it has to ignore, and a member an engine
    ignores is how an engine comes to install one by accident. What that costs
    is one more read of one file, by the reader that needs it, at the start of a
    run — and `PackInvalid` is raised for a declaration this reader cannot read,
    so the refusal is the same refusal the same mistake gets everywhere else.
    """
    manifest_file = pack.directory / manifest.MANIFEST_FILE
    try:
        document = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, RecursionError) as unreadable:
        raise manifest.PackInvalid(
            f"{manifest_file} does not read as a manifest: {unreadable}"
        ) from unreadable
    declared: dict[int, tuple[str, ...]] = {}
    points = document.get("point")
    if not isinstance(points, list):
        return declared
    interposed = {point.audit_event for point in pack.points}
    for index, entry in enumerate(points):
        if not isinstance(entry, dict) or UNINTERPOSED not in entry:
            continue
        named = entry[UNINTERPOSED]
        if (
            not isinstance(named, list)
            or not named
            or not all(isinstance(event, str) and event for event in named)
        ):
            raise manifest.PackInvalid(
                f"[[point]] {index + 1} {UNINTERPOSED} is {named!r}: a point names the audit "
                f"events by which an effect of its kind reaches the world along a path it does "
                f"not interpose, as a non-empty list of event names — a verifier that cannot "
                f"read them would drop the very effects it exists to account for"
            )
        borrowed = sorted(set(named) & interposed)
        if borrowed:
            raise manifest.PackInvalid(
                f"[[point]] {index + 1} {UNINTERPOSED} names {borrowed[0]!r}, which a point of "
                f"this pack interposes: one event is watched or it is missed, and a pack "
                f"declaring it both ways declares nothing this verifier can act on"
            )
        declared[index] = tuple(dict.fromkeys(named))
    return declared


def inner_events(pack: manifest.Pack) -> dict[int, tuple[str, ...]]:
    """The uninterposed events a pack declares its own interposed call raises, by point.

    A call a point interposes can reach its effect through an event the same
    pack names as a path it does not interpose — a library creating the process
    it was asked for through a lower-level call the pack also names. Counting
    that event would report the one act the point judged as a second act nobody
    judged. Which events those are is the library's vocabulary, so the pack
    names them (article 4), and `the_same_act` says when one is paired.

    An inner event must be one the same point names as uninterposed: pairing
    only ever stops a named event from being counted, and a declaration of one
    side alone declares nothing this verifier can act on.
    """
    manifest_file = pack.directory / manifest.MANIFEST_FILE
    try:
        document = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError, RecursionError) as unreadable:
        raise manifest.PackInvalid(
            f"{manifest_file} does not read as a manifest: {unreadable}"
        ) from unreadable
    declared: dict[int, tuple[str, ...]] = {}
    points = document.get("point")
    if not isinstance(points, list):
        return declared
    uninterposed = uninterposed_events(pack)
    for index, entry in enumerate(points):
        if not isinstance(entry, dict) or INNER not in entry:
            continue
        named = entry[INNER]
        if (
            not isinstance(named, list)
            or not named
            or not all(isinstance(event, str) and event for event in named)
        ):
            raise manifest.PackInvalid(
                f"[[point]] {index + 1} {INNER} is {named!r}: a point names the events its own "
                f"interposed call raises on the way to its effect, as a non-empty list of event "
                f"names"
            )
        stray = sorted(set(named) - set(uninterposed.get(index, ())))
        if stray:
            raise manifest.PackInvalid(
                f"[[point]] {index + 1} {INNER} names {stray[0]!r}, which the same point does "
                f"not name in {UNINTERPOSED}: pairing only stops a named event from being "
                f"counted, so an inner event is always one of the point's uninterposed events"
            )
        declared[index] = tuple(dict.fromkeys(named))
    return declared


def _the_inner_events(packs: Sequence[manifest.Pack]) -> dict[str, frozenset[str]]:
    """For each interposed event, the inner events of the points that interpose it."""
    inner: dict[str, frozenset[str]] = {}
    for pack in packs:
        declared = inner_events(pack)
        for index, point in enumerate(pack.points):
            named = declared.get(index)
            if named:
                inner[point.audit_event] = inner.get(point.audit_event, frozenset()) | set(named)
    return inner


def _the_paths_no_point_interposes(
    packs: Sequence[manifest.Pack], watched: Sequence[Watched]
) -> dict[str, list[Watched]]:
    """Every declared uninterposed event, against the points whose coverage it touches.

    The walk is by position, because `watched` is built from the same packs in
    the same order: a point's declaration belongs to that point's own count, and
    an effect that slipped past one pack says nothing about another's.

    """
    uninterposed: dict[str, list[Watched]] = {}
    at = 0
    for pack in packs:
        declared = uninterposed_events(pack)
        for index in range(len(pack.points)):
            item = watched[at]
            at += 1
            for event in declared.get(index, ()):
                uninterposed.setdefault(event, []).append(item)
    return uninterposed


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
    correlation: str | None,
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
                correlation=correlation,
                # One recorded decision per effect is the proof, so nothing is
                # answered from a grant: a repeated effect asks again.
                hold_grants=False,
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

    Rule C4: the transport re-opens no address on a caller's behalf, and a
    daemon may close the connection after any answer — the one this client was
    written against keeps it open after a document and closes it after a
    stream, which is a behaviour and not a promise. Re-verifying before every
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


class Judged(NamedTuple):
    """The call judged last on one thread, kept for the one inner event it may raise next."""

    #: The events its points name as their own call's implementation (`inner_events`).
    inner: frozenset[str]
    #: What its audit event carried.
    arguments: tuple[object, ...]


def _argument_vector(value: object) -> tuple[str, ...] | None:
    """An argument vector as the names it holds, or `None` for a shape that is not one.

    Only a list or a tuple is read. Iterating anything else could run the
    program's own code, or use up an argument the call it belongs to was about
    to consume — and a hook that did either would change the effect it watches.
    """
    if isinstance(value, str | bytes | os.PathLike):
        value = (value,)
    if not isinstance(value, list | tuple):
        return None
    try:
        return tuple(os.fsdecode(item) for item in value)
    except (TypeError, ValueError):
        return None


def the_same_act(judged: Judged, event: str, arguments: tuple[object, ...]) -> bool:
    """Whether `event` is the implementation of the call just judged, not an act of its own.

    It is when the judged call's points name it as an inner event and it carries,
    as its second argument, the argument vector the judged call's own event
    carried as its second — the process a spawning call was asked to create,
    against the process the lower-level call beneath it creates. Anything else
    is another act, and is counted as the path around the pack it is.

    Which event counts as NEXT is the caller's rule, not this function's:
    `_consulting` offers a judged call only to the very next event its thread
    raises.
    """
    if event not in judged.inner or len(judged.arguments) < 2 or len(arguments) < 2:
        return False
    spawned = _argument_vector(arguments[1])
    return spawned is not None and spawned == _argument_vector(judged.arguments[1])


def _consulting(
    chain: Chain,
    by_event: Mapping[str, list[Watched]],
    uninterposed: Mapping[str, list[Watched]],
    watch: Watch,
    inner: Mapping[str, frozenset[str]],
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

    **An event a pack named as a path it does NOT interpose is counted and let
    through.** It is an effect of a kind the pack names, so a report that
    dropped it published a point's verdict — earned by the calls that DID go
    through the interposed attribute — as if it were the whole of the run.
    Counting it makes the coverage of that claim visibly incomplete. Stopping
    it would do something else entirely: `instrument run` does not interpose
    that path, so a `verify` that blocked it would be stricter than the mode it
    measures, and this software is a governance and observability layer and not
    a confinement mechanism (article 2). The limit that instrumentation can miss
    a call stays exactly as true and exactly as documented; what ends is the
    silence about it.

    **Except the one its judged call raises itself.** A point may name, among
    those events, the ones its own call raises on the way to the effect it was
    asked for (`inner_events`). Such an event is not counted when it is the
    VERY NEXT event the judging thread raises after the call it judged let
    through, and `the_same_act` says it is that call's own. Next means next: a
    thread's judged call is taken by whatever that thread raises after it, so
    an inner event raised later, or a second one, is counted like any other.
    """

    # The call judged last on each thread, taken by the next event that thread
    # raises — whatever that event is.
    last_judged: dict[int, Judged] = {}

    def consult(event: str, arguments: tuple[object, ...]) -> None:
        # Empty unless a judged call is waiting for its next event, so every
        # other event still costs one check here.
        judged = last_judged.pop(threading.get_ident(), None) if last_judged else None
        if not watch.judging:
            # Either nothing has been handed over yet, or the hand-off is still
            # locating and reading the program. Both are the watch's question
            # and not this function's; the second is also where the gate opens.
            watch.opening(arguments)
            return
        points = by_event.get(event)
        missed = uninterposed.get(event)
        if points is None and missed is None:
            return
        whose = watch.whose(arguments)
        if whose == THE_HAND_OFFS:
            return
        if missed is not None and (judged is None or not the_same_act(judged, event, arguments)):
            for item in missed:
                item.not_judged(PATH_NOT_INTERPOSED)
            sys.stderr.write(f"{NOT_JUDGED}: {event}: {PATH_NOT_INTERPOSED}\n")
        if points is None:
            return
        if whose == NOT_JUDGED:
            # No chain read and no raise: nothing was established about this
            # event, and inventing either answer would be a verdict nobody
            # measured. It is counted on every point the event would have been
            # judged against, which is what makes the run not a pass.
            for item in points:
                item.not_judged(A_START_FILE)
            return
        with watch.ours():
            for item in points:
                _judge(chain, item, watch)
        # Judged and let through: its own inner event, if it raises one, is the
        # next event this thread raises. A judgement that stopped the call
        # raised above, and a call that was stopped raises nothing further.
        named = inner.get(event)
        if named:
            last_judged[threading.get_ident()] = Judged(named, arguments)

    return consult


def _judge(chain: Chain, item: Watched, watch: Watch) -> None:
    """One point, against one consultation of the chain.

    Four endings, in the one order that cannot flatter the run. A record of
    this run's supports the effect. A chain that answered nothing ends the run
    with « could not read » and no finding. Evidence that could not be used, or
    a walk that never reached the chain's end, leaves the effect NOT JUDGED —
    aborted, counted, and never a finding, because a negative fact needs the
    whole chain read. Only what is left is a finding, and it needs the walk to
    have finished.
    """
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
        # Some reads were answered and the last was not. What is concluded below
        # is made of what WAS read, and the failure is said beside it rather than
        # folded into it: a reader has to be able to see that the chain went
        # away while this run was concluding.
        sys.stderr.write(
            f"the chain was read and then stopped answering: {consultation.problem.message}\n"
        )
    unusable = consultation.unusable
    if unusable is None and not consultation.established_absence:
        unusable = WALK_INTERRUPTED
    if unusable is not None:
        _stopped_unjudged(item, unusable)
    if consultation.foreign:
        sys.stderr.write(
            f"a record for {item.point.capability} exists in this scope and was recorded for "
            f"another principal, so it is not a decision that preceded this effect\n"
        )
    item.refused = True
    raise RuntimeError(f"{UNGOVERNED} effect: {item.point.capability} ({item.point.audit_event})")


def _stopped_unjudged(item: Watched, reason: str) -> None:
    """Abort an effect this run could not judge, count it, and make no finding.

    The abort is the same caution an ungoverned effect gets — an effect whose
    governance could not be established is not one this harness may let through
    — and the silence about the program is the difference: `refused` stays
    false, the verdict stays about the events that WERE judged, and the count
    is what refuses the run a pass (`verify._exit_for`).
    """
    item.not_judged(reason)
    sys.stderr.write(
        f"{NOT_JUDGED}: {item.point.capability} ({item.point.audit_event}): {reason}\n"
    )
    raise NotJudged(
        f"this effect is not judged and was stopped: "
        f"{item.point.capability} ({item.point.audit_event}): {reason}"
    )


def _consulted(chain: Chain, capability: str) -> Consultation:
    """Poll the chain for a record this effect has not already been answered by.

    Polled, because article 10 writes the chain asynchronously: the record of
    an effect the plane allowed may arrive after the effect was allowed to
    happen.

    Everything a walk could not establish is remembered across the patience, and
    remembered SEPARATELY. A consultation that read nothing at all has
    established nothing about the program; one whose every walk stopped half way
    has established nothing either; one that saw a record it could not take has
    established nothing about that record. None of the three is an absence, and
    an absence is the only one of them that is a finding.
    """
    deadline = time.monotonic() + CHAIN_WAIT
    read_something = False
    established_absence = False
    foreign = False
    problem: Problem | None = None
    unusable: str | None = None
    with chain.lock:
        while True:
            walk = _matching(chain, capability)
            read_something = read_something or walk.answered
            established_absence = established_absence or walk.whole
            foreign = foreign or walk.foreign
            if walk.problem is not None:
                problem = walk.problem
            if walk.unusable is not None:
                unusable = walk.unusable
            if walk.matched is not None:
                return Consultation(walk.matched, True, True, None, None, foreign)
            if time.monotonic() >= deadline:
                return Consultation(
                    None, read_something, established_absence, problem, unusable, foreign
                )
            time.sleep(POLL_INTERVAL)


def _matching(chain: Chain, capability: str) -> Walk:
    """One walk of the chain for a record of THIS run's effect of this kind.

    Nothing is inferred from a read that was not answered, and nothing is
    inferred from a walk that did not finish: both are carried out to the caller
    rather than left to look like « no record exists ».

    **What makes a record this effect's, and what this walk cannot establish.**
    An entry is a candidate when it is an effect of the asked capability that
    the plane allowed, at a position after the floor that no consultation has
    already spent. A candidate becomes a SUPPORT only when it was recorded for
    the account this process runs as, out of a range the chain's own
    verification reports intact, and — where this run's own boundary is what
    asked — on the one connection this run's records come from. Everything
    those three refuse is said in one of two ways, and the difference matters:
    a record of another principal is not this run's at all, so the absence of
    one is still establishable and a finding may still be made; a record this
    run cannot verify, or cannot tell from another execution's, leaves the
    question open and no finding may be made from it.

    **What this walk still cannot check, said here because it is the gap.** It
    does not compare the arguments of the call with the digest the record
    carries, so two effects of one kind, one principal and one connection are
    not told apart. Which arguments identify an effect is the pack's
    declaration and the boundary's digest (article 11), and a pack publishes no
    way to render them for anything but its own wrapper — so a verifier that
    computed one would be a second policy, drifting from the first and
    producing findings nobody made. `docs/PACKS.md` states the limit.
    """
    answered = False
    unusable: str | None = None
    foreign = False
    from_sequence = chain.floor + 1
    while True:
        result = reads.read(lambda at=from_sequence: _one_page(chain, at))
        if not isinstance(result, Answered):
            return Walk(None, answered, False, result.problem, unusable, foreign)
        answered = True
        entries, served, next_from = result.value
        intact = served.get("condition") == INTACT
        for entry in entries:
            sequence = entry.get("sequence")
            body = entry.get("body")
            if (
                not isinstance(sequence, int)
                or sequence <= chain.floor
                or sequence in chain.spent
                or entry.get("kind") != EFFECT
                or not isinstance(body, Mapping)
                or body.get("capability") != capability
                or body.get("outcome") != ALLOW
            ):
                continue
            if not _recorded_for(chain.principals, entry):
                # Somebody else's decision. Said, and stepped over: an absence
                # of this run's own records is still an absence.
                foreign = True
                continue
            if not intact:
                unusable = unusable or EVIDENCE_NOT_INTACT
                continue
            if not _this_runs_correlation(chain, body):
                unusable = unusable or ANOTHER_EXECUTIONS_RUN
                continue
            chain.spent.add(sequence)
            return Walk(sequence, True, True, None, None, foreign)
        if next_from is None:
            return Walk(None, answered, True, None, unusable, foreign)
        from_sequence = next_from


def _recorded_for(principals: frozenset[str], entry: Mapping[str, object]) -> bool:
    """Whether the plane recorded this entry for the account this process runs as.

    An entry whose principal cannot be read is not read as this run's: an
    identity this client could not establish is not an identity it may assume
    (article 2).
    """
    principal = entry.get("principal")
    if not isinstance(principal, Mapping):
        return False
    named = principal.get("id")
    return isinstance(named, str) and named in principals


def _this_runs_correlation(chain: Chain, body: Mapping[str, object]) -> bool:
    """Whether this effect record carries the correlation this run's boundary stamped.

    Asked only where this run's own boundary is what asked. The token is this
    harness's own, generated before the program started and handed to the
    boundary, so a record is this run's when the plane recorded that same token
    on it — which the plane does as `correlation_source: boundary_supplied`.
    Nothing here trusts the thing it proves: the boundary does not choose the
    token and the harness does not read it back from a record to learn it. A
    record whose correlation is absent, another value, or unreadable is a record
    this run cannot tell from another execution's, and the FIRST record is held
    to the token exactly as every later one is.

    A run that stamped no token (`chain.correlation is None`) required none: that
    is `--ungoverned`, where the chain alone answers and every record is another
    execution's by construction.
    """
    if not chain.one_execution or chain.correlation is None:
        return True
    return body.get("correlation") == chain.correlation


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
