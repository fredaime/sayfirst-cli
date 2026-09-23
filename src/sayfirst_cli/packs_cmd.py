# SPDX-License-Identifier: Apache-2.0
"""`sayfirst packs`: list and check the convenience packs this distribution ships.

Article 9's packs are designated by the person who runs them: by a path, or by
the name a pack ships under here, and `instrument/designation.py` is the whole
of that rule (`docs/PACKS.md` says why it is not a registry). This command is
the other side of it: `list` prints, for each pack this distribution ships
beside itself, the name `--pack` takes, what it asks about, and where it is, so
a person has something to read rather than something to guess; `check` reads a
designation the same way the engine will, before a program is ever run with it.

Neither verb ends in a traceback. A pack that does not read is named with the
member and the rule it broke, and the exit code says so — for `list` as much as
for `check`, since the command a person uses to discover what is shipped is the
one that has to be able to say that something shipped is broken.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from . import exit_codes
from .instrument import designation, manifest
from .instrument.designation import shipped_packs as shipped_packs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sayfirst packs",
        description="List and check the convenience packs this distribution ships (article 9).",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("list", help="one line per shipped pack: name, capabilities, path")
    checking = verbs.add_parser("check", help="read one pack the way the engine will")
    checking.add_argument(
        "path",
        metavar="PACK",
        help="a shipped pack's name, or the path of a pack directory (./own-pack)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    stdout = out or sys.stdout
    stderr = err or sys.stderr
    forwarded = list(sys.argv[1:] if argv is None else argv)
    arguments = build_parser().parse_args(forwarded)
    if arguments.verb == "list":
        return _list(stdout, stderr)
    return _check(arguments.path, stdout, stderr)


def _list(stdout: TextIO, stderr: TextIO) -> int:
    """One line per shipped pack: its name, every capability it declares, its path.

    A pack whose manifest will not read is named on stderr with the rule it
    broke — what `check` does with the one pack it is given — and the listing
    goes on, so the packs after it in sort order are still printed. The exit
    code is the misuse `check` uses, because a listing that omitted a broken
    pack and exited 0 would render an absence as a healthy state (article 2),
    and because a traceback out of this client is never how a pack's problem is
    reported.

    64 for a pack the *distribution* ships is the honest half of the answer
    rather than a perfect fit — the caller typed nothing wrong, and something
    this command named cannot be read. `exit_codes.py` states the widened
    reading beside the number, and says why a code of its own would cost more
    than it bought: no caller can act differently on the two.
    """
    unread = 0
    for directory in shipped_packs():
        try:
            pack = manifest.read_pack(directory)
        except manifest.PackInvalid as invalid:
            stderr.write(f"invalid {directory}: {invalid}\n")
            unread += 1
            continue
        capabilities = " ".join(dict.fromkeys(point.capability for point in pack.points))
        stdout.write(f"{pack.name} {capabilities} {directory}\n")
    return exit_codes.EXIT_MISUSE if unread else 0


def _check(named: str, stdout: TextIO, stderr: TextIO) -> int:
    """Read one pack, the way `instrument run` and `verify` will, before anything runs.

    The same designation `--pack` takes, read by the same function, so that a
    `check` that passes is a `run` that will read the same pack — and then the
    two members only the verifier reads, by the verifier's own readers, so that
    it is a `verify` that will read it too.
    """
    try:
        pack = designation.read(named)
        # Imported here: the verifier's readers sit beside the hook that uses
        # them, and `packs list` has no need of either.
        from .instrument import harness

        harness.inner_events(pack)  # which reads `uninterposed_events` first
    except manifest.PackInvalid as invalid:
        stderr.write(f"{invalid}\n")
        return exit_codes.EXIT_MISUSE
    stdout.write(f"ok {pack.name}\n")
    return 0
