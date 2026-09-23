# SPDX-License-Identifier: Apache-2.0
"""A target that names its interpreter is run by that interpreter, and by no other.

A governed program runs INSIDE the interpreter that installs the boundary: the
engine replaces attributes in a live process, so there is no governing from the
outside. When this command and the program share an environment that is the end
of it. When they do not — this command installed as a tool of its own, the
program living in its project's environment — a target spelled the way a person
runs it every day, `python app.py`, leaves two honest readings and one
dishonest one. Refusing the word is honest and useless. Dropping the word and
running `app.py` here is the dishonest one: the program would run under an
interpreter nobody named, without its own dependencies, while the command line
said otherwise (article 2). What this module does is the third: **the whole
command is handed to the interpreter that was named.**

Handed over means replaced: this process becomes `<that interpreter> … sayfirst
instrument <verb> …` with the word removed, by `exec`, so the streams, the
signals and the exit status are the program's exactly as they are in-process,
and nothing here stays behind to translate them. Everything after that is the
ordinary path, in that interpreter: the same packs, the same profile, the same
launcher, the boundary in front of the program before its first import.

**What is lent, and what is not.** That interpreter has to be able to import
this client, the boundary and the contract, and its environment may hold none
of them. They are lent by LOCATION and by NAME: a finder placed first on its
import machinery answers for exactly those three top-level names, each from the
directory this process imported it from, and answers for nothing else. This
environment's site directory is never put on that interpreter's path, so no
other package installed beside this command becomes importable by the program,
and none of the program's own can be shadowed. The three are pure Python with
no dependency outside themselves (articles 13 and 14 — the closure guard
measures it), which is what makes lending them by name sufficient. They answer
first on purpose: a program that holds its own copy of the boundary would
otherwise run this client against a contract of another version.

**What decides that a word names an interpreter** is its spelling, as for a
pack: a first word whose last path component is `python`, `python3` or
`python3.N`. A bare one is looked up the way a shell would; one with a
separator is that file. A script that is really called `python3` is run as
`python ./python3`, like anywhere else.

**An executable script hands over by its shebang.** A console-script agent is
started as `myagent`, not as `python -m myagent`, and its file begins
`#!/path/to/.venv/bin/python`. So when the target's first word is an executable
file whose shebang names a Python — including `#!/usr/bin/env python3` — that
Python runs it, the same hand-off a leading `python` word triggers, and for the
same reason: the boundary belongs in the interpreter the program actually runs
in. A shebang that names this same interpreter changes nothing; a non-executable
file, or a shebang that is a shell or a wrapper, is left to run as the source it
already was.

**A runner in the first position is refused.** `uv run`, `poetry run` and their
kind start an interpreter this launcher has not chosen and cannot install the
boundary into ahead of time, so handing the runner over would govern nothing.
It is refused with the two spellings that do work: name the interpreter, or ask
the runner for it once, outside the governed command.

**What it costs**, stated rather than discovered: the named interpreter is
asked for its version first (one short process), because a Python older than
this client's floor cannot even parse it and the refusal should be a sentence
here, not a syntax error there; and interpreter options (`-u`, `-X …`) are not
carried — the target grammar stays « a script, or `-m` and a module », and an
option in that place is refused as the unknown script it would be.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from . import launch

#: The oldest interpreter that can hold this client. `pyproject.toml` states the
#: same floor as `requires-python`; this is the copy a running process can read,
#: and `tests/test_interpreter_target.py` holds the two together.
MINIMUM: Final[tuple[int, int]] = (3, 12)

#: The first interpreter too new for what is lent: every lent distribution
#: declares `requires-python` below it, and a package installed on an
#: interpreter it does not declare is one nobody measured there. Held to
#: `pyproject.toml` the same way as the floor.
BEYOND: Final[tuple[int, int]] = (3, 15)

#: What is lent to a named interpreter: this client and the two distributions it
#: depends on, each as the package that is imported and the distribution whose
#: metadata says which release it is. Nothing else is ever lent.
#:
#: The metadata is lent because the contract reads its OWN release from it when
#: it is imported (the deprecation window of a generation is dated by release),
#: and an installed package whose metadata cannot be found does not import at
#: all. It is lent the way the packages are: by name, from one location, and a
#: listing of « every distribution installed » is never answered from here.
LENT: Final[dict[str, str]] = {
    "sayfirst_cli": "sayfirst-cli",
    "sayfirst_boundary": "sayfirst-boundary",
    "sayfirst_contract": "sayfirst-contract",
}

#: The two members of what is handed to the bootstrap.
_PACKAGES: Final[str] = "packages"
_DISTRIBUTIONS: Final[str] = "distributions"

#: What a target may be, said once for the two verbs that take one. A help text is
#: a claim about what is read, so the interpreter word is in it.
TARGET_HELP: Final[str] = (
    "after `--`: SCRIPT [args] or -m MODULE [args], run inside this command's own "
    "interpreter; led by an interpreter's name (python app.py, .venv/bin/python -m pkg), "
    "or an executable script whose shebang names one (./myagent), it is run by that "
    "interpreter instead; a runner (uv run, poetry run) is refused"
)

#: How long a named interpreter has to say which version it is.
PROBE_SECONDS: Final[float] = 20.0

_INTERPRETER_WORD: Final = re.compile(r"^python(3(\.\d+)?)?$")

#: The attribute the bootstrap's finder carries, which is how a process learns
#: that it is running on lent packages and has to lend them on in turn.
_MARK: Final[str] = "sayfirst_lent_locations"

#: Set in the environment of the interpreter a target was handed to, so that the
#: `sayfirst instrument` this launcher runs THERE does not choose an interpreter
#: all over again. Without it the handed-over command reads its target's first
#: word a second time: an executable whose shebang names yet another interpreter
#: is exec'd away from the one just chosen, and an interpreter that resolves to a
#: forwarding shim (its path never equal to the real `sys.executable`) is handed
#: over on every pass and loops. The mark is READ ONCE and removed, so a program
#: that itself runs `sayfirst instrument` is unaffected, and it is set only for
#: the process being exec'd — never for the followed children of `follow.py`.
CHOSEN_VARIABLE: Final[str] = "SAYFIRST_INTERPRETER_CHOSEN"

#: What runs first in the named interpreter. It receives the lent locations as
#: its first argument, what to run as its second, and the arguments after that.
#:
#: The interpreter is started with `-P`, so nothing of the working directory is
#: on the import path while this client imports itself; a placeholder then takes
#: the head of the path, because the launcher REPLACES the head with what the
#: interpreter would have put there for the program (`launch._hand_off`) and
#: must find something there that is its to replace. The placeholder names no
#: directory, so nothing can be imported from it in the meantime.
_BOOTSTRAP: Final[str] = f"""\
import json, sys
from importlib.machinery import PathFinder

class _Lent:
    {_MARK} = json.loads(sys.argv[1])

    @classmethod
    def find_spec(cls, name, path=None, target=None):
        where = cls.{_MARK}[{_PACKAGES!r}].get(name) if path is None else None
        return None if where is None else PathFinder.find_spec(name, [where])

    @classmethod
    def find_distributions(cls, context=None):
        from importlib.metadata import DistributionFinder, MetadataPathFinder
        name = getattr(context, "name", None)
        where = cls.{_MARK}[{_DISTRIBUTIONS!r}].get(str(name).replace("_", "-").lower())
        if name is None or where is None:
            return iter(())
        return MetadataPathFinder.find_distributions(
            DistributionFinder.Context(name=name, path=[where])
        )

sys.meta_path.insert(0, _Lent)
sys.path.insert(0, {launch.HANDED_OVER_HEAD!r})
kind, arguments = sys.argv[2], sys.argv[3:]
if kind == "command":
    import os
    os.environ[{CHOSEN_VARIABLE!r}] = "1"
    from sayfirst_cli.main import main
    raise SystemExit(main(arguments))
import runpy
sys.argv = [kind, *arguments]
runpy.run_module(kind, run_name="__main__", alter_sys=True)
"""

#: The second argument that asks for this client's own command line.
_COMMAND: Final[str] = "command"

#: Runners that start an interpreter of their OWN, in an environment they pick.
#: A program named through one of these cannot be governed by handing IT over —
#: the boundary has to be installed inside the interpreter the program runs in,
#: and a runner has not chosen that interpreter yet. So a runner in the first
#: position is refused with the spelling that does work: name the interpreter.
RUNNERS: Final[frozenset[str]] = frozenset(
    {"uv", "poetry", "pdm", "hatch", "pipenv", "rye", "pixi", "tox", "nox"}
)

#: How many bytes of a file are read to look for a shebang. A shebang the kernel
#: honours is on the first line; a line longer than this is not one it would run.
_SHEBANG_BYTES: Final[int] = 512


def named_in(target: Sequence[str]) -> str | None:
    """The first word of a target if it is spelled as an interpreter, else `None`."""
    if not target:
        return None
    return target[0] if _INTERPRETER_WORD.fullmatch(Path(target[0]).name) else None


def _refuse_a_runner(target: Sequence[str]) -> None:
    """A runner in the first position names no interpreter this launcher can govern in.

    `uv run app.py`, `poetry run app.py` and their kind start a fresh interpreter
    the runner selects, and the boundary cannot be in it before it starts. Rather
    than hand the runner over — which would run this whole command inside the
    runner and govern nothing — it is refused with the two spellings that work:
    name the interpreter directly, or ask the runner for it once, outside.
    """
    if len(target) >= 2 and Path(target[0]).name in RUNNERS and target[1] == "run":
        runner = Path(target[0]).name
        raise launch.LaunchMisuse(
            f"this launcher cannot govern a program started by {runner!r}: a runner starts an "
            f"interpreter of its own, and the boundary has to be installed inside the interpreter "
            f"the program runs in. Name that interpreter instead — `.venv/bin/python app.py`, or "
            f"`$({runner} run which python) app.py`"
        )


def shebang_interpreter(script: str) -> str | None:
    """The Python an executable script's shebang names, as an absolute path, or None.

    A shebang matters only for a file the kernel would execute directly, so this
    is consulted only for an executable file. `#!/usr/bin/env python3.12` and
    `#!/path/to/python` are both read; a shebang that names anything but a Python
    — a shell, `env -S …`, a wrapper — answers None, and the file is left to run
    as the Python source a target without an interpreter word already is. One
    that names a Python which is not there is refused: the system would refuse
    to run the script, and another Python running it is nobody's program. When
    the Python it names is THIS interpreter, the caller runs the script in
    process exactly as before; the hand-off happens only for another one.
    """
    path = Path(script)
    if not (path.is_file() and os.access(path, os.X_OK)):
        return None
    try:
        with open(path, "rb") as opened:
            first = opened.read(_SHEBANG_BYTES).split(b"\n", 1)[0]
    except OSError:
        return None
    if not first.startswith(b"#!"):
        return None
    try:
        words = first[2:].decode("utf-8").split()
    except UnicodeDecodeError:
        return None
    if not words:
        return None
    # `#!/usr/bin/env python3` names the interpreter in the second word; a bare
    # `env` with no argument, or `env -S …`, names nothing this reads.
    candidate = words[1] if Path(words[0]).name == "env" and len(words) >= 2 else words[0]
    if candidate.startswith("-") or not _INTERPRETER_WORD.fullmatch(Path(candidate).name):
        return None
    resolved = candidate if os.path.isabs(candidate) and os.path.exists(candidate) else None
    resolved = resolved or shutil.which(candidate)
    if not resolved:
        # A Python the kernel would not find either: it refuses the script, and
        # running it under this command's own interpreter instead would be the
        # dishonest reading this module exists to refuse.
        raise launch.LaunchMisuse(
            f"{script}: its first line names {candidate!r}, and there is no such interpreter "
            f"here — the system would refuse to run it, so this launcher does too rather than "
            f"run it under another Python"
        )
    return os.path.abspath(resolved)


def selection(target: Sequence[str]) -> tuple[str, list[str]] | None:
    """Which interpreter runs this target, and the program to run there, or None.

    None means « run it in this command's own interpreter », which is the
    unchanged path for a script, a `-m` module, and an executable whose shebang
    is not a Python. Otherwise the pair is the interpreter and the program handed
    to it: for an interpreter word the program is everything after the word; for
    an executable script the program is the whole target, because the script
    itself is what that interpreter runs. A runner in the first position raises
    rather than returning, for the reason `_refuse_a_runner` gives.
    """
    if not target or target[0] == launch.MODULE_FORM:
        return None
    word = named_in(target)
    if word is not None:
        return locate(word), list(target[1:])
    _refuse_a_runner(target)
    shebang = shebang_interpreter(target[0])
    if shebang is not None:
        return shebang, list(target)
    return None


def locate(word: str) -> str:
    """The interpreter a word names, as an absolute path, or the misuse that it names none."""
    found = shutil.which(word)
    if found is None:
        raise launch.LaunchMisuse(
            f"this launcher found no interpreter at {word!r}: a target whose first word is "
            f"spelled like one is run by that interpreter, and there is none to run it"
        )
    return os.path.abspath(found)


def is_this_one(executable: str) -> bool:
    """Whether an interpreter is the one already running this command.

    Compared as names and never resolved: an environment's `python` is a link
    to the interpreter it was made from, so two environments resolve to one
    file while being two different answers to « which packages are there ».
    Saying no to a second spelling of this same environment costs one `exec`
    into the environment we are already in, and changes nothing else.
    """
    return os.path.abspath(executable) == os.path.abspath(sys.executable)


def lent_locations() -> dict[str, dict[str, str]]:
    """Where this process holds what it lends: each package, and each distribution's metadata.

    The two are asked for separately because they are not always one directory:
    a distribution installed for development keeps its metadata in the
    environment and its package in a source tree.

    A process that is itself running on lent packages lends the same locations
    on, rather than working them out again from modules a finder placed.
    """
    inherited = _inherited()
    if inherited is not None:
        return {member: dict(found) for member, found in inherited.items()}
    packages: dict[str, str] = {}
    distributions: dict[str, str] = {}
    for package, distribution in LENT.items():
        origin = getattr(importlib.import_module(package), "__file__", None)
        try:
            metadata = importlib.metadata.distribution(distribution).locate_file("")
        except importlib.metadata.PackageNotFoundError:
            metadata = None
        if not isinstance(origin, str) or metadata is None:
            raise launch.LaunchMisuse(
                f"this launcher cannot lend {distribution!r} to another interpreter: it is "
                f"not installed from a directory here, so there is no location to lend"
            )
        packages[package] = str(Path(origin).resolve().parent.parent)
        distributions[distribution] = str(Path(str(metadata)).resolve())
    return {_PACKAGES: packages, _DISTRIBUTIONS: distributions}


def _inherited() -> dict[str, dict[str, str]] | None:
    for finder in sys.meta_path:
        lent = getattr(finder, _MARK, None)
        if isinstance(lent, dict):
            return lent
    return None


#: What the version probe prints around the two numbers, so its own line can be
#: found however much an interpreter's start-up wrote before it. A marker rather
#: than « the whole of stdout is the version » — a target whose `sitecustomize`
#: announces itself on start-up is a usable interpreter, not a malformed version.
_VERSION_MARK: Final[str] = "sayfirst-version:"


def version_of(executable: str) -> tuple[int, int]:
    """The version an interpreter says it is, or the misuse that it would not say.

    Probed with `-I`, so the interpreter runs isolated — no `site`, no
    `sitecustomize`, no `PYTHONSTARTUP`, nothing of the environment — and cannot
    print anything of its own around the answer. The answer is still found by its
    marker rather than by reading the whole of stdout, because `-I` suppresses
    the ordinary start-up files but not, say, a `usercustomize` a build wrote
    into the standard library, and a version query has no business being that
    fragile. `-I` here changes nothing about how the program itself later starts
    — that is `_hand_off`'s doing, under the interpreter's normal start-up.
    """
    try:
        finished = subprocess.run(
            [
                executable,
                "-I",
                "-c",
                f"import sys; print('{_VERSION_MARK}', sys.version_info[0], sys.version_info[1])",
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_SECONDS,
            check=False,
        )
        line = next(row for row in reversed(finished.stdout.splitlines()) if _VERSION_MARK in row)
        _, major, minor = line.rsplit(maxsplit=2)
        return int(major), int(minor)
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError) as unusable:
        raise launch.LaunchMisuse(
            f"this launcher could not ask {executable!r} which Python it is: {unusable}"
        ) from unusable


def holds_this_client(executable: str) -> bool:
    """Whether an interpreter imports this client and the two it depends on by itself.

    What `--follow-children` needs of the interpreter a program's children run:
    the packages lent to the program's own process live in that process's
    finder, and a child is a fresh process with none. Asked with `-P`, so the
    answer is the interpreter's and not the working directory's.
    """
    try:
        finished = subprocess.run(
            [executable, "-P", "-c", "import " + ", ".join(sorted(LENT))],
            capture_output=True,
            timeout=PROBE_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return finished.returncode == 0


def command_in(executable: str, kind: str, *arguments: str) -> list[str]:
    """The command line that runs something of this client inside another interpreter."""
    return [executable, "-P", "-c", _BOOTSTRAP, json.dumps(lent_locations()), kind, *arguments]


def module_command(module: str, *arguments: str) -> list[str]:
    """How this process starts one of this client's own modules in a second process.

    `sys.executable -m module` wherever this client is installed in the running
    interpreter. In an interpreter that was LENT it, that spelling finds
    nothing — the second process starts with no finder — so the lending is
    handed on with the command.
    """
    if _inherited() is None:
        return [sys.executable, "-m", module, *arguments]
    return command_in(sys.executable, module, *arguments)


def hand_the_command_to(
    executable: str,
    arguments: Sequence[str],
    *,
    follow_children: bool = False,
    execv: Callable[[str, list[str]], object] = os.execv,
) -> None:
    """Become `executable`, running this client's own command line there.

    `arguments` is everything after `sayfirst`. On success this does not
    return: the process is replaced, and the code a shell reads is whatever that
    command line answers. It raises `LaunchMisuse` — before anything is handed
    over — for an interpreter this client cannot run in, and, with
    `follow_children`, for one whose children could not install the boundary.
    """
    found = version_of(executable)
    if found < MINIMUM:
        raise launch.LaunchMisuse(
            f"this launcher cannot run the program under {executable!r}: it is Python "
            f"{found[0]}.{found[1]}, and the boundary has to be installed inside the "
            f"interpreter the program runs in, which takes Python "
            f"{MINIMUM[0]}.{MINIMUM[1]} or later"
        )
    if found >= BEYOND:
        raise launch.LaunchMisuse(
            f"this launcher cannot run the program under {executable!r}: it is Python "
            f"{found[0]}.{found[1]}, and what it would lend that interpreter declares Python "
            f"before {BEYOND[0]}.{BEYOND[1]}"
        )
    if follow_children and not holds_this_client(executable):
        raise launch.LaunchMisuse(
            f"--follow-children cannot follow the program's children under {executable!r}: "
            f"this client is not installed there, and what is lent to the program's own "
            f"process is not lent to a child it starts, so every Python child would fail at "
            f"start-up. Install this client in that interpreter, or run without the flag"
        )
    command = command_in(executable, _COMMAND, *arguments)
    sys.stdout.flush()
    sys.stderr.flush()
    execv(executable, command)
