# SPDX-License-Identifier: Apache-2.0
"""`--follow-children`: a governed program's Python children govern their effects too.

The engine installs the boundary in ONE process — the one the launcher hands the
program to. A program that spawns another Python (a worker, a tool, a step of
its own) starts a fresh interpreter with no boundary in it, and every effect
that child makes reaches the world unasked. `instrument run` already governs the
SPAWN itself (the subprocess pack asks before the child is created); what it does
not do, on its own, is govern what the child then does.

`--follow-children` closes that, for `run`, by the mechanism a fresh interpreter
offers for running code before a program's own: a `sitecustomize` on its import
path. When the flag is set, the launcher prepends this package's `_bootstrap`
directory to `PYTHONPATH` and writes the run's configuration into the
environment. A Python child that starts normally WITH THAT ENVIRONMENT then
imports the `sitecustomize` there, which installs the same packs, against the
same daemon, before the child's code runs — and leaves the environment in
place, so a grandchild started the same way is followed too.

**A child that installs the boundary and cannot, fails closed.** Once
`sitecustomize` runs, a child that cannot install the boundary — the daemon
unreachable at import, a pack that will not read, this client not importable in
the child — raises out of `sitecustomize` and the child interpreter exits before
the program runs. A followed child that got that far makes its effect asked
about or does not run.

**What the mechanism cannot reach, stated rather than hidden.** The install
rides on the environment and the interpreter's ordinary start-up, so a child
that does not start with both is not followed and runs as it would have
WITHOUT the flag — the same as a child of a run that did not pass
`--follow-children`:

* a child started with `-S` (no site), `-I` (isolated) or `-E` (ignore the
  environment) never imports the `sitecustomize`;
* a child whose environment REPLACES `PYTHONPATH` — the everyday
  `env={**os.environ, "PYTHONPATH": …}` — or is built from nothing never sees
  the bootstrap directory on it, though the configuration variable may still be
  there.

This is the boundary of an environment-and-start-up mechanism, not a hole the
flag opens: the child's own SPAWN was still governed by the pack in the parent
(the parent asked before creating it), and what such a child then does is
beyond the reach of anything installed through the environment. It is a limit,
not a fail-open, and the regression suite pins both shapes so they stay known
limits rather than surprises.

**What it needs, and what it does not reach.** The child must be able to import
this client, the boundary and the contract. That holds when they are installed
in the interpreter the child runs (the ordinary `uv tool install` case). It does
NOT hold when this command was itself lent those packages for a target
interpreter (`interpreter.py`): the lending lives in one process's meta-path and
a spawned child is a fresh process, so `--follow-children` with a named
interpreter that lacks an install is refused rather than silently followed by
nothing. A non-Python child is not a Python child: the spawn was governed, and
there is no interpreter to install into.

**Only `run`.** `verify` proves one process from its own audit hook, and a
spawned child is a separate process the hook cannot see (`harness.py` counts such
a child as coverage this run could not judge). Following children would govern
them without letting the proof see them, which is why the flag is `run`'s.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from .manifest import Pack

#: The environment member that carries the run's configuration to a child. Its
#: presence is what tells a `sitecustomize` this is a followed run.
CONFIG_VARIABLE: Final[str] = "SAYFIRST_FOLLOW_CHILDREN"

#: The directory whose `sitecustomize.py` a child imports at startup. It ships
#: beside this module, in the installed distribution, and carries nothing but
#: that one file.
BOOTSTRAP_DIRECTORY: Final[str] = "_bootstrap"


def bootstrap_path() -> Path:
    """Where the child's `sitecustomize` lives, in this installed distribution."""
    return Path(__file__).resolve().parent / BOOTSTRAP_DIRECTORY


def configuration(
    packs: Sequence[Pack],
    *,
    socket: str,
    scope: str,
    mode: str,
    daemon_user: str | None,
    principal: str | None,
) -> str:
    """The run's configuration a child reads back, as JSON.

    The pack DIRECTORIES, not the packs: a child reads each again, because it
    shares no state with this process and a pack that stopped reading between the
    parent and the child is the child's to refuse. Everything a child needs to
    build the same profile and the same boundary, and nothing about verification
    — a followed child is governed, never proven.

    **The directories are made absolute.** A child spawned in a working
    directory of its own — an ordinary `subprocess.run(..., cwd=…)` — reads a
    relative `./own-pack` against ITS cwd, not the parent's, and finds no pack
    there: it would fail closed on a pack that was fine where the parent
    designated it. Resolved here, once, against the parent's working directory,
    so the name a child reads is the pack the parent chose.
    """
    return json.dumps(
        {
            "packs": [str(pack.directory.resolve()) for pack in packs],
            "socket": socket,
            "scope": scope,
            "mode": mode,
            "daemon_user": daemon_user,
            "principal": principal,
        },
        sort_keys=True,
    )


def environment_for(
    base: Mapping[str, str],
    packs: Sequence[Pack],
    *,
    socket: str,
    scope: str,
    mode: str,
    daemon_user: str | None,
    principal: str | None,
) -> dict[str, str]:
    """`base` with the child bootstrap on the import path and the run configured.

    `PYTHONPATH` gets this package's `_bootstrap` directory at its HEAD, so the
    child imports that `sitecustomize` and not another; the directory holds only
    `sitecustomize.py`, so nothing else of this client's is put on a child's
    path by being there. Everything else is left as it was — `PYTHONSAFEPATH`
    included, which keeps a script's own directory off the head of the path and
    does not stop a `sitecustomize` on `PYTHONPATH` from loading.
    """
    updated = dict(base)
    bootstrap = str(bootstrap_path())
    existing = updated.get("PYTHONPATH", "")
    updated["PYTHONPATH"] = f"{bootstrap}{os.pathsep}{existing}" if existing else bootstrap
    updated[CONFIG_VARIABLE] = configuration(
        packs,
        socket=socket,
        scope=scope,
        mode=mode,
        daemon_user=daemon_user,
        principal=principal,
    )
    return updated
