# SPDX-License-Identifier: Apache-2.0
"""Hand a program to the interpreter with the boundary already in front of it.

The order is the whole of it: the target, the connection, the boundary, the
engine, and only then the program. Whatever the program loads afterwards
arrives instrumented; a reference it bound before this ran does not, and that
limit belongs to the verifier rather than to a claim made here.

## The line between this client's failures and the program's

It is drawn at the hand-off, and it is the only line that matters here.

**Before the hand-off every failure is this client's**, because the program has
not started: a pack that does not read, a point the engine refuses, an
execution module that will not load or whose wrapper cannot be made, a script
that is not there, a name `-m` cannot find. Each of those is a mistake in the
invocation, each is raised as `LaunchMisuse`, and the caller renders it as the
misuse it is. None of them is an outcome — no question was ever put — so
reporting one with a code that means « denied » would be the invented verdict
articles 1 and 2 forbid between them.

**After the hand-off every failure is the program's**, and nothing is
translated. A refusal raised at the boundary is the program's exception to
catch, and a program that catches none of them ends the way any Python program
ending on an exception ends. `SystemExit` is read exactly as the interpreter
reads it. Exactly one failure crosses the line, and it is named where it
happens: a point whose module is imported LATER, naming an attribute that
module has not got, is discovered inside the program's own import — `engine.py`
says why it cannot be found any sooner.

The program keeps this process's own streams, because they are the streams it
would have had, and it gets the `sys.path` entry and the `sys.argv` the
interpreter would have given it for the form it was named in. The two streams
this function is given are the launcher's; it writes to one of them only where
the interpreter itself would write.
"""

from __future__ import annotations

import atexit
import importlib.util
import os
import pwd
import runpy
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Final, TextIO

from sayfirst_boundary import Boundary
from sayfirst_contract.binding.http_unix_socket.client import SocketClient
from sayfirst_contract.transport.socket_client import SocketProfile, expected_principal_uid

from . import follow
from .engine import Engine, EngineMisuse
from .manifest import Pack

#: How long one question may take. Longer than a read's, because a governed
#: program's first act waits for a decision with nobody watching the terminal.
ASK_TIMEOUT: Final[float] = 10.0

#: The spelling that names a module rather than a file, taken from the
#: interpreter rather than invented, so that one form is typed one way.
MODULE_FORM: Final[str] = "-m"

#: The head of the import path in an interpreter this command was handed to:
#: the hand-over's bootstrap puts it there, and `_hand_off` replaces it with
#: what that interpreter would have put there for the program. It names no
#: directory, so nothing can be imported from it in the meantime.
HANDED_OVER_HEAD: Final[str] = "<sayfirst: the launcher replaces this entry>"

#: What a caller is told at the last instant before the hand-off: which files
#: are the program's OWN, which the hand-off reads to reach them, and which of
#: the second the import system derives further names from. Nothing else is
#: promised, and nothing is promised about what happens afterwards — see
#: `_hand_off`.
#:
#: Three facts rather than one, because they answer different questions. The
#: first is a moment: everything the interpreter does before it executes one of
#: the program's own files is this launcher locating and reading a program, and
#: no path names all of it. The second is a set of paths and is true whenever
#: it fires. The third exists because a bytecode cache is written under a name
#: the import system invents from the cache's own, which nothing here can know
#: in advance and only a derivation can match. An earlier revision held a
#: module `runpy` imports on first use, so that import would land before the
#: caller was told; the moment makes that unnecessary, because the import is
#: before it.
Starting = Callable[[tuple[str, ...], tuple[str, ...], tuple[str, ...]], None]


class LaunchMisuse(ValueError):
    """This invocation cannot be launched, and the program has not started.

    Raised only BEFORE the hand-off, which is the whole of its meaning: what
    comes after belongs to the program. The caller renders it as a misuse and
    never as an outcome, because there is no answer to report.

    Its sentences name « this launcher » and never a verb. Two verbs hand a
    program over through this file now, and a sentence that named one of them
    would tell half the readers to go and fix a command they never typed.
    """


@dataclass(frozen=True)
class Program:
    """The target as the interpreter would have received it.

    `module` is set for the `-m` form and `None` otherwise, where `argv[0]` is
    the script. One field rather than two, so there is no third state.
    """

    argv: tuple[str, ...]
    #: What the interpreter puts at the head of the import path for this form.
    first_on_the_path: str
    module: str | None = None


def run(
    packs: Sequence[Pack],
    profile: SocketProfile,
    target: Sequence[str],
    *,
    principal: str | None = None,
    correlation: str | None = None,
    follow_children: bool = False,
    hold_grants: bool = True,
    out: TextIO,
    err: TextIO,
    starting: Starting | None = None,
) -> int:
    """Install the boundary in front of the program, then run the program.

    The client is the one that can HOLD what it is granted: article 10 binds a
    grant to the connection the answer arrived on, and only the binding's own
    client keeps that connection open. A transport that closes in its `finally`
    answers the question correctly and kills the grant in the same call.

    The target is resolved before the connection is arranged, so a mistyped
    program name is reported without anything being asked of the daemon.

    The profile's scope reaches the engine, which supplies it to every ask a
    pack makes: a scope somebody typed and a scope nobody typed must not be the
    same question on the wire.

    `starting` is called once, at the last instant before the program runs and
    after everything this launcher does for itself — the engine's load of each
    pack's execution module included. A caller that has to tell its own work
    from the program's cannot draw that line from outside.

    `hold_grants=False` asks for every effect and holds no grant. The verifier
    runs this way: its proof is one recorded decision for each effect it saw,
    and a grant hit — an identical effect answered by an earlier allow, which is
    what `run` does (article 10) — records nothing, so a repeated effect would
    read as ungoverned.
    """
    program = _the_program(list(target))
    client = SocketClient(
        socket_path=Path(profile.socket_path),
        expected_uid=expected_principal_uid(profile),
        timeout=ASK_TIMEOUT,
    )
    boundary = Boundary(
        client=client,
        principal_reference=principal or _this_account(),
        # Set only by the verifier, which stamps one run and matches records on
        # it (`harness.py`). The launcher's own governed mode leaves it None: a
        # run is not a proof, and nothing reads a correlation back from it.
        correlation=correlation,
        hold_grants=hold_grants,
    )
    try:
        # The engine is deliberately not kept: the interposition's scope is this
        # process, and `uninstall` exists for a caller that wants it back
        # sooner — not for this one, which has nothing left to do afterwards.
        Engine().install(list(packs), boundary, scope=profile.scope)
    except EngineMisuse as refused:
        # The pack was designated on the command line, so a pack the engine
        # refuses is this invocation's mistake and not the program's failure.
        raise LaunchMisuse(str(refused)) from refused
    if follow_children:
        # Arranged in THIS process's environment, right before the program
        # starts, so every Python child the program spawns installs the same
        # boundary before its own code runs (`follow.py`). Set here rather than
        # earlier so it is not inherited by anything this launcher spawns for
        # itself; the program is the only thing started after this.
        os.environ.update(
            follow.environment_for(
                os.environ,
                list(packs),
                socket=profile.socket_path,
                scope=profile.scope,
                mode=profile.mode,
                daemon_user=profile.daemon_user,
                principal=principal,
            )
        )
    return _hand_off(program, err, starting)


def _the_head_for(program: Program) -> list[str]:
    """What the interpreter would have put at the head of the import path for the program.

    Its directory — for `-m`, the working directory — unless the person asked
    for a safe path (`-P`, `PYTHONSAFEPATH`), which puts nothing there. In this
    command's own interpreter the head is then an entry of the person's own,
    and it is kept: replacing it took a real directory off the path and the
    program's import of it failed. Handed over, the flag is the hand-over's own
    `-P`, the head is its placeholder, and the person's setting is read off the
    environment that interpreter was given.
    """
    if sys.path and sys.path[0] == HANDED_OVER_HEAD:
        return [] if os.environ.get("PYTHONSAFEPATH") else [program.first_on_the_path]
    if sys.flags.safe_path:
        return sys.path[:1]
    return [program.first_on_the_path]


def hand_over(target: Sequence[str], *, err: TextIO, starting: Starting | None = None) -> int:
    """Run the program with nothing in front of it, as the interpreter would.

    `run` is the governed hand-off; this is the same hand-off without the
    boundary. The verifier needs it, because what a proof measures has to be
    the program the interpreter would have run — every rule about `sys.path`,
    `sys.argv` and the reading of `SystemExit` is the one `run` uses, since it
    is the same code and not a second reading of the target written beside it.

    Nothing is installed and no connection is arranged, so a target that names
    no program is still `LaunchMisuse` and still arrives before anything runs.
    """
    return _hand_off(_the_program(list(target)), err, starting)


def this_account() -> str:
    """Who this process is, in the one spelling the boundary uses for a person.

    Never sent as a credential: the daemon establishes identity from the peer of
    the connection (article 6). This is what the holder compares a grant's own
    condition against, locally. Public because a followed child builds its own
    boundary and needs the same spelling this one uses (`follow.py`).

    A uid no account database names — a container started under an arbitrary
    uid — is spelled by its number, which is how the daemon names such a peer.
    """
    uid = os.geteuid()
    try:
        return f"user:{pwd.getpwuid(uid).pw_name}"
    except KeyError:
        return f"user:{uid}"


#: Kept for readers inside this module.
_this_account = this_account


def _the_program(target: list[str]) -> Program:
    """The target, resolved into what the interpreter would have been given.

    A script is checked here, because the check needs nothing but the file
    system. A name given to `-m` is checked in `_hand_off` instead, once the
    import path is the one the program will have: looked up on any other path it
    would be a different question with a different answer.
    """
    if not target:
        raise LaunchMisuse(
            "this launcher needs a program to run after `--`: either `-m MODULE` and "
            "its arguments, or a script and its arguments"
        )
    if target[0] == MODULE_FORM:
        if len(target) < 2:
            raise LaunchMisuse(
                f"this launcher was given `{MODULE_FORM}` with no module name after it"
            )
        named = target[1]
        return Program(argv=(named, *target[2:]), first_on_the_path=os.getcwd(), module=named)
    script = target[0]
    if not Path(script).is_file():
        raise LaunchMisuse(
            f"this launcher found no file to run at {script!r}: a target that does not "
            f"begin `{MODULE_FORM}` is a script this process can read"
        )
    return Program(argv=(script, *target[1:]), first_on_the_path=str(Path(script).resolve().parent))


def _hand_off(program: Program, err: TextIO, starting: Starting | None = None) -> int:
    """Run the program as the main module, and read its ending as the interpreter does.

    `sys.path` and `sys.argv` are set to what the interpreter would have given
    the program for the form it was named in — the script's own directory, or
    the working directory for `-m` — because a governed program is the same
    program, and one that cannot import the module beside it is not being
    governed, it is being broken.

    **They are put back when the PROGRAM ends, which is not when its main
    module returns.** A handler it registered to run at exit, and a thread it
    started and did not join, are both the program's own code and both run
    afterwards; under verification later still, because the harness runs them
    itself rather than leaving them to the interpreter. Measured as the defect:
    a handler reading `sys.argv` was handed the `sayfirst` command line instead
    of the program's arguments, and `import` of the module beside the program
    raised `ModuleNotFoundError` — an ordinary program changed by being
    governed, over something it never asked the boundary about.

    So the restore is registered with `atexit` BEFORE the program starts, and
    `atexit` runs its register last in, first out: every handler the program
    registers afterwards runs ahead of it, and the interpreter runs the
    program's surviving threads out before any of them. It is registered
    rather than called at the end, so it happens however the program ended —
    returning, raising, or `SystemExit` — and on the verifier's path as well,
    where `atexit._run_exitfuncs` reaches it before the findings are written.

    A program that leaves NOTHING behind is finished when its main module
    returns, and its state is put back there, in the `finally` — the same
    instant as before. That is not a hedge, it is the same rule read at the
    only moment it can be read: nothing of the program is left to see it.
    What « nothing » means is asked of the interpreter — no thread of the
    program's still running, nothing added to the exit register — and a
    program that leaves either keeps its state until both are done with.

    `starting` is called after the name has been resolved and the import path
    arranged, and immediately before the interpreter is handed the program. It
    is told three things: every file that is the program's OWN — the script, or
    the module's file, or, for a package, BOTH its `__init__` and its
    `__main__` — and every file the hand-off reads to reach them, and which of
    those are bytecode caches. The cache locations are asked of
    `importlib.util.cache_from_source` rather than spelled here.

    A package's `__init__` is the program's own code and it runs first, which
    is why it is named as such and not merely as a file read on the way: a
    caller told to start watching at the `__main__` would miss every effect the
    `__init__` made. Measured before it was: a package whose `__init__` spawned
    and whose `__main__` spawned, against a chain holding one decision, was
    reported as governed with both processes run.

    What no path can name is what the import system DERIVES twice over: it
    writes a cache by creating a file named after that cache plus a number of
    its own, and it writes through a bare descriptor that names no file at all.
    The number is why the caches are named apart from the rest; the descriptor
    is why the moment is reported as well as the paths.
    """
    restore = _putting_back(list(sys.argv), list(sys.path))
    # Before the program starts, so the register's last-in-first-out order puts
    # this after everything the program adds to it.
    atexit.register(restore)
    registered, running = atexit._ncallbacks(), _the_threads_running_now()
    # Assigned as a slice, so a path with nothing on it is added to rather than
    # subscripted. Every import this launcher needs is already done.
    sys.path[:1] = _the_head_for(program)
    try:
        if program.module is not None:
            origins = _refuse_a_name_that_names_no_module(program.module, starting)
            sys.argv = list(program.argv)
            # Every origin is the program's own: for a package, the `__init__`
            # that runs on the way to the `__main__` is its code too.
            _starting(starting, origins, *_the_hand_offs_own_files(origins))
            runpy.run_module(program.module, run_name="__main__", alter_sys=True)
        else:
            sys.argv = list(program.argv)
            _starting(starting, (program.argv[0],), (program.argv[0],), ())
            runpy.run_path(program.argv[0], run_name="__main__")
    except SystemExit as ending:
        return _ending(ending.code, err)
    finally:
        if not _the_program_outlives_its_main_module(registered, running):
            atexit.unregister(restore)
            restore()
    return 0


def _putting_back(argv: list[str], path: list[str]) -> Callable[[], None]:
    """The launcher's own arguments and import path, restored once and once only.

    Once, because it can be reached twice: the verifier's harness runs the exit
    register itself and the interpreter runs what is left of it afterwards, and
    two hand-offs in one process leave two of these in the register. Each one
    puts back what IT saw, and the innermost runs first, so a process ends with
    the state it started with however many programs it ran.

    `sys.argv` is rebound and `sys.path` is assigned into, exactly as they were
    taken: something else may be holding the list object the path came in.
    """
    put_back = False

    def restore() -> None:
        nonlocal put_back
        if put_back:
            return
        put_back = True
        sys.argv = list(argv)
        sys.path[:] = list(path)

    return restore


def _the_threads_running_now() -> frozenset[int]:
    """Every thread alive at this instant, by the identity `threading` gives it."""
    return frozenset(thread.ident for thread in threading.enumerate() if thread.ident is not None)


def _the_program_outlives_its_main_module(registered: int, running: frozenset[int]) -> bool:
    """Whether anything of the program is still to come, asked of the interpreter.

    Two things outlive a main module and both are the program's own code: a
    handler it registered to run at exit, and a thread it started that the
    interpreter will wait for. Neither is asked about by name — the exit
    register cannot be read and a thread does not say who started it — so each
    is read as a CHANGE since the hand-off began: the register grew, or a
    non-daemon thread is running that was not running before.

    A daemon thread is not one of them. The interpreter does not wait for one
    either; it ends it at shutdown, so holding the program's state for one
    would be holding it for something that may never finish.

    It errs towards saying no, and that is the direction to err in here: a no
    puts the launcher's state back at the instant this function is asked, which
    is where it was always put back before any of this existed.
    """
    if atexit._ncallbacks() > registered:
        return True
    current = threading.current_thread()
    return any(
        thread is not current
        and not thread.daemon
        and thread.is_alive()
        and thread.ident not in running
        for thread in threading.enumerate()
    )


def _starting(
    starting: Starting | None,
    starts: Sequence[str],
    own: Sequence[str],
    caches: Sequence[str],
) -> None:
    """Say which files are the program's own, and which the hand-off's."""
    if starting is not None:
        starting(tuple(starts), tuple(own), tuple(caches))


def _the_hand_offs_own_files(origins: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Each source the hand-off reads, and where the import system keeps its cache.

    Answered as two sets, because the caller does two different things with
    them: a source is matched by its own name, while a cache is matched by its
    name AND by the name the import system derives from it to write through.

    Asked of the import system rather than spelled: a cache path computed by
    hand would be right for one interpreter, one optimisation level and one
    layout, and wrong the first time any of the three changed.

    A source the import system has no cache location for contributes only
    itself — there is then no cache to name, which is an answer and not a
    failure.
    """
    own: list[str] = []
    caches: list[str] = []
    for origin in origins:
        own.append(origin)
        try:
            cache = importlib.util.cache_from_source(origin)
        except (NotImplementedError, ValueError):
            continue
        own.append(cache)
        caches.append(cache)
    return tuple(own), tuple(caches)


def _refuse_a_name_that_names_no_module(
    named: str, starting: Starting | None = None
) -> tuple[str, ...]:
    """Refuse a `-m` name this interpreter cannot find, before `runpy` reaches it.

    `runpy` reports the same absence as an `ImportError` out of the middle of
    this launcher, which reaches a shell as a traceback and exit 1 — this
    client's published code for « denied ». A mistyped name is not a denial, so
    it is found here and said as the misuse it is.

    A lookup that RAISES is read exactly like one that finds nothing: a name
    whose parent cannot even be consulted is not a program this run can hand
    over, whatever the reason it could not be consulted.

    It answers with the files the lookup found, because the lookup is the only
    place they are known: `_hand_off` passes them on and nothing recomputes
    them on a different import path, which would be a different question with
    a different answer.

    **Resolved one segment at a time, from the top, because looking a dotted
    name up RUNS the packages above it.** `find_spec('a.b')` executes `a`'s own
    `__init__`, and `find_spec('a.__main__')` executes `a`'s: that is the
    program's code and not this launcher's preparation. So `starting` is told
    what is known before every step that can run any of it, and told again
    afterwards — the second call closes a watcher's gate over the part that is
    this launcher's work again, which is why the two are not one. Measured
    before this existed: a package whose `__init__` spawned and whose
    `__main__` spawned, against a chain holding one decision, was reported as
    `governed` with both processes run.

    **The window this leaves, measured rather than stated.** Telling the caller
    again is also what SHUTS its gate, because the file of the next segment is
    not yet in the set it excludes — so between the end of one `__init__` and
    the first statement of what comes after it, everything is attributed to the
    hand-off: not judged, not counted, not aborted. What is inside the stretch
    is this launcher's own lookup of the next segment and the import of its
    file, plus anything the program's own code runs during them — a finder the
    `__init__` installed, or a thread it started. It is entered once per
    remaining segment and nowhere else.

    Its width, measured on one machine with
    `tests/test_instrument_verify.py::test_the_between_segments_window_is_measured_and_named`'s
    own shape — a two-segment `-m` name, cold, thirty runs — was 57 to 88
    microseconds, median 61. The number is a machine's and the shape is not,
    which is why the test asserts the second and this paragraph records the
    first.

    It is measured rather than guarded on purpose. Keeping the gate open across
    the remaining lookups would judge this launcher's own reading of files it
    has not yet been able to name, and telling a program's effect from the
    hand-off's inside the stretch needs the watch to know about threads it did
    not start — which it cannot. The direction it fails in is the unsafe one:
    an effect in the stretch is dropped rather than counted, so it leaves no
    `unjudged` behind it. Recorded here, and named in the report as a limit, so
    that it is a known cost rather than a surprise.
    """
    origins: list[str] = []
    parts = named.split(".")
    for depth, _ in enumerate(parts):
        if depth:
            # Looking this segment up runs the package above it.
            _starting(starting, tuple(origins), *_the_hand_offs_own_files(origins))
        found = _the_spec_of(".".join(parts[: depth + 1]), named)
        if isinstance(found.origin, str):
            origins.append(found.origin)
    if found.submodule_search_locations is not None:
        # A package runs through its `__main__`; one without is not a program,
        # and `runpy` would say so as a traceback from the middle of this
        # launcher. Looking it up runs the package's own `__init__`.
        _starting(starting, tuple(origins), *_the_hand_offs_own_files(origins))
        entry = _the_spec_of(f"{named}.__main__", named, in_the_package=named)
        if isinstance(entry.origin, str):
            origins.append(entry.origin)
    return tuple(origins)


def _the_spec_of(prefix: str, named: str, *, in_the_package: str | None = None) -> ModuleSpec:
    """What the interpreter finds for one name, or the misuse that it finds nothing."""
    try:
        found = importlib.util.find_spec(prefix)
    except (ImportError, AttributeError, TypeError, ValueError) as unusable:
        raise LaunchMisuse(
            f"this launcher cannot look up {prefix!r} to run it: {unusable}"
        ) from unusable
    if found is None:
        if in_the_package is not None:
            raise LaunchMisuse(
                f"this launcher found no `__main__` in the package {in_the_package!r}: a package "
                f"runs through its `__main__` module, and this one has none"
            )
        raise LaunchMisuse(
            f"this launcher found no module named {named!r} to run: `{MODULE_FORM}` names "
            f"a module on the import path the program would have had"
        )
    return found


def _ending(code: object, err: TextIO) -> int:
    """`SystemExit` as the interpreter reads it: absent is zero, a number is itself.

    Anything else the interpreter prints and exits 1 on, so that is what happens
    here too. It is the one line this launcher writes to a stream of its own, and
    it writes what the program said rather than a sentence about it.
    """
    if code is None:
        return 0
    if isinstance(code, int):
        return int(code)
    err.write(f"{code}\n")
    return 1
