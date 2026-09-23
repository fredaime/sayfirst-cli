# SPDX-License-Identifier: Apache-2.0
"""What a followed child runs before its own program: it installs the boundary, or dies.

This file is imported automatically by any Python whose import path has this
directory at its head — which `follow.environment_for` arranges for the children
of a `sayfirst instrument run --follow-children` (see `follow.py`). It reads the
run's configuration from the environment, installs the same packs against the
same daemon, and then hands control on to whatever `sitecustomize` was already
there. With no configuration it does nothing, so this directory sitting on a
path harms no unrelated interpreter.

**It fails closed.** Anything that stops the boundary going in — the packs, the
profile, this client not importable here — is raised, and the child interpreter
exits before the program runs. A followed child governs its effects or it does
not run. The engine is left installed for the life of the child, and the
environment is left as it was, so a grandchild is followed too.
"""

from __future__ import annotations

import os


def _install_the_boundary() -> None:
    """Install the run's packs against its daemon, in this child interpreter."""
    import json
    from pathlib import Path

    # Imported here, not at module top: this file is imported by EVERY child of a
    # followed run, and one that carries no configuration must cost nothing and
    # must not need this client importable at all.
    from sayfirst_boundary import Boundary
    from sayfirst_contract.binding.http_unix_socket.client import SocketClient
    from sayfirst_contract.transport.socket_client import (
        SocketProfile,
        expected_principal_uid,
    )

    from sayfirst_cli.instrument import follow, launch, manifest
    from sayfirst_cli.instrument.engine import Engine

    configured = json.loads(os.environ[follow.CONFIG_VARIABLE])
    packs = [manifest.read_pack(Path(directory)) for directory in configured["packs"]]
    profile = SocketProfile(
        configured["socket"],
        mode=configured["mode"],
        daemon_user=configured["daemon_user"],
        scope=configured["scope"],
    )
    client = SocketClient(
        socket_path=Path(profile.socket_path),
        expected_uid=expected_principal_uid(profile),
        timeout=launch.ASK_TIMEOUT,
    )
    boundary = Boundary(
        client=client,
        principal_reference=configured["principal"] or launch.this_account(),
    )
    Engine().install(packs, boundary, scope=profile.scope)


def _hand_on_to_any_prior_sitecustomize() -> None:
    """Run a `sitecustomize` that was on the path behind this one, if there is one.

    Following children must not silently disable a site's own start-up file.
    Rather than scan for a literal `sitecustomize.py` — which misses a
    `sitecustomize` PACKAGE and loads a source file under a private name that
    breaks any code looking itself up in `sys.modules` (a dataclass with
    postponed annotations, for one) — this hands off through Python's OWN import
    resolution: it removes this bootstrap directory from the import path and this
    module from `sys.modules`, then imports `sitecustomize` again. Whatever
    Python would have found had this directory not been first — a module or a
    package — is found and registered exactly as start-up would have registered
    it. The bootstrap directory stays on the child's `PYTHONPATH` for its own
    children (that is the environment, not this process's `sys.path`), so a
    grandchild is still followed.
    """
    import importlib
    import sys

    here = os.path.realpath(os.path.dirname(__file__))
    kept = [entry for entry in sys.path if os.path.realpath(entry) != here]
    if len(kept) == len(sys.path):
        return  # this bootstrap was not reached through a directory we can drop
    saved_path, sys.path[:] = list(sys.path), kept
    saved_module = sys.modules.pop("sitecustomize", None)
    try:
        importlib.import_module("sitecustomize")
    except ImportError:
        # No other `sitecustomize` on the path: there was nothing to chain to.
        if saved_module is not None:
            sys.modules.setdefault("sitecustomize", saved_module)
    finally:
        sys.path[:] = saved_path


if os.environ.get("SAYFIRST_FOLLOW_CHILDREN"):
    try:
        _install_the_boundary()
    except BaseException as failure:  # a followed child fails closed on any setup error
        raise SystemExit(
            "sayfirst: this child of a --follow-children run could not install the "
            f"boundary, so it will not run ungoverned: {failure}"
        ) from failure

_hand_on_to_any_prior_sitecustomize()
