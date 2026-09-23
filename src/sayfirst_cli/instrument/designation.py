# SPDX-License-Identifier: Apache-2.0
"""How a pack is designated on the command line: by a path, or by the name it ships under.

Article 9: a pack is « explicitly designated by the user », and there is no
registry. Both halves bind here, and this file is where the line between them
is drawn.

**A path is a directory, read as it always was.** Any designation with a path
separator in it — and `.` and `..`, which are paths with none — names a
directory a person chose, exactly as they would name a file to run.

**A bare word is the name of a pack THIS DISTRIBUTION ships, and nothing else.**
It is looked up in one place: the package data installed beside this module,
the same set `sayfirst packs list` prints. That is a designation — the person
typed the pack they want — and it is not a registry, because every property a
registry would have is absent on purpose:

* no search path. One location is read, and it is not configurable: no
  environment variable, no file, no directory of the user's is consulted.
* no fallback between the two readings. Which one applies is decided by the
  SPELLING alone, before the file system is looked at, so the same words mean
  the same thing in every directory. A bare word is never tried as a directory
  of the working directory — a directory somebody left beside a program cannot
  become the code that runs in front of it — and a path is never tried as a
  name.
* no default set. A pack nobody designated is not installed.
* no name anybody else can publish under. The set is closed by what this
  distribution carries; a pack of one's own is designated by its path.

A word that names nothing shipped is refused, saying what is shipped and how a
directory is spelled. It is refused rather than retried as a path for the
reason above, and because « not found, so something else was used » is the one
answer a designation must never give.

(Like the modules beside it, this file names no pack and no library: the names
are whatever the package data holds, read when they are asked for.)
"""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
from typing import Final

from . import manifest

#: The package whose data is the packs this distribution ships.
SHIPPED_PACKAGE: Final[str] = "sayfirst_cli.packs"

#: What `--pack` says about itself, in one place for the two verbs that take it.
HELP: Final[str] = (
    "a pack: the name of one this distribution ships (`sayfirst packs list`), or the path "
    "of a pack directory, spelled with a separator (./own-pack); repeat for each pack"
)

#: The two spellings that are paths without a separator in them.
_RELATIVE: Final[frozenset[str]] = frozenset({".", ".."})


def shipped_packs() -> list[Path]:
    """Every pack directory this installed distribution carries, sorted by path.

    A directory counts as a pack candidate here by carrying a manifest, not by
    its name — `__pycache__` and anything else beside the packs is silently
    not a pack rather than a reason this call fails; `manifest.read_pack`
    still refuses one that names a manifest but is not, in fact, complete.

    Read from the *installed* package with `importlib.resources`, never from a
    path built off this file's own location: the packs this answers with are
    the ones this distribution actually carries, wherever it was installed.
    """
    root = importlib.resources.files(SHIPPED_PACKAGE)
    if not root.is_dir():
        return []
    return sorted(
        Path(str(item))
        for item in root.iterdir()
        if item.is_dir() and (item / manifest.MANIFEST_FILE).is_file()
    )


def is_a_path(designation: str) -> bool:
    """Whether a designation is spelled as a path, asked of the spelling alone."""
    separators = (os.sep, os.altsep) if os.altsep else (os.sep,)
    return designation in _RELATIVE or any(mark in designation for mark in separators)


def directory_of(designation: str) -> Path:
    """The directory a designation names, or the refusal that says why it names none.

    A path is answered as it was typed and is not looked at here: whether it
    holds a pack is `manifest.read_pack`'s question, asked next, with its own
    sentences. A name is answered with the shipped directory of that name.
    """
    if is_a_path(designation):
        return Path(designation)
    shipped = {path.name: path for path in shipped_packs()}
    if designation in shipped:
        return shipped[designation]
    names = ", ".join(sorted(shipped)) or "none"
    raise manifest.PackInvalid(
        f"no pack of that name ships with this distribution (it ships: {names}). A bare "
        f"word is the name of a shipped pack and is never read as a directory; a pack of "
        f"your own is designated by a path with a separator in it, as in ./{designation}"
    )


def read(designation: str) -> manifest.Pack:
    """The pack a designation names, read the way the engine will read it."""
    return manifest.read_pack(directory_of(designation))
