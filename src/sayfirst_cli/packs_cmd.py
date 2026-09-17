# SPDX-License-Identifier: Apache-2.0
"""`sayfirst packs`: list and check the convenience packs this distribution ships.

Article 9's packs are designated by path, never by name — `instrument run
--pack` reads only the directory a person types, and consults no registry, no
default set and no name resolution of its own (`docs/PACKS.md`). This command
does not change that: `list` prints, for each pack this distribution ships
beside itself, the one path `--pack` would accept for it, so a person has
something to copy rather than something to guess; `check` reads a path the
same way the engine will, before a program is ever run with it.

Neither verb ends in a traceback. A pack that does not read is named with the
member and the rule it broke, and the exit code says so — for `list` as much as
for `check`, since the command a person uses to discover what is shipped is the
one that has to be able to say that something shipped is broken.

Read from the *installed* package with `importlib.resources`, never from a
path built off this file's own location: the packs this prints are the ones
this distribution actually carries, wherever it was installed.
"""

from __future__ import annotations

import argparse
import importlib.resources
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from . import exit_codes
from .instrument import manifest


def shipped_packs() -> list[Path]:
    """Every pack directory this installed distribution carries, sorted by path.

    A directory counts as a pack candidate here by carrying a manifest, not by
    its name — `__pycache__` and anything else beside the packs is silently
    not a pack rather than a reason this call fails; `manifest.read_pack`
    still refuses one that names a manifest but is not, in fact, complete.
    """
    root = importlib.resources.files("sayfirst_cli.packs")
    if not root.is_dir():
        return []
    return sorted(
        Path(str(item))
        for item in root.iterdir()
        if item.is_dir() and (item / manifest.MANIFEST_FILE).is_file()
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sayfirst packs",
        description="List and check the convenience packs this distribution ships (article 9).",
    )
    verbs = parser.add_subparsers(dest="verb", required=True)
    verbs.add_parser("list", help="one line per shipped pack: name, capabilities, path")
    checking = verbs.add_parser("check", help="read one pack directory the way the engine will")
    checking.add_argument("path", metavar="PATH", help="the pack directory to read")
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
    return _check(Path(arguments.path), stdout, stderr)


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


def _check(path: Path, stdout: TextIO, stderr: TextIO) -> int:
    """Read one pack, the way `instrument run` will, before anything is run with it."""
    try:
        pack = manifest.read_pack(path)
    except manifest.PackInvalid as invalid:
        stderr.write(f"{invalid}\n")
        return exit_codes.EXIT_MISUSE
    stdout.write(f"ok {pack.name}\n")
    return 0
