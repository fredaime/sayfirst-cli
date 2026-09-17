# SPDX-License-Identifier: Apache-2.0
"""Article 15: the wheel this repository publishes reproduces the notices.

Article 15 asks that every repository carry "a NOTICE that redistributions
reproduce", and a wheel on an index is the redistribution most people will ever
hold: nobody who installs this client reads this tree. The licence and the
notice travel in it today by the build backend's own defaults, which is exactly
why this is held rather than trusted — a default is a decision nobody made, and
an exclude pattern added here for some other reason would drop both from what
leaves under a tag, silently and without a red run anywhere.

Two readings, because the wheel says it twice and either alone can be true while
the other is false: the metadata DECLARES the files (`License-File:`, which is
what a tool asks), and the archive CARRIES them (under `licenses/`, which is
what a person reading a redistribution opens). Bytes are compared rather than
names, so a notice that shipped emptied is not a notice that shipped.

Built into a directory of its own under the test's own temporary path, never the
tree's `dist/`: a guard that wrote there would make the next release's build
read what a test left behind. One rule per file, as the control plane's twin
guard is, so a new rule arrives as a new file and a new file never conflicts.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

#: The notices every redistribution of this repository carries, at its root.
NOTICES = ("LICENSE", "NOTICE")


def _build_the_wheel(into: Path) -> Path:
    """The wheel `uv build` makes of this repository, built where nothing reads it."""
    subprocess.run(
        ("uv", "build", "--wheel", "--out-dir", str(into)),
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = sorted(into.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def test_the_shipped_wheel_declares_and_carries_the_repository_notices(tmp_path: Path) -> None:
    """Article 15: the redistribution an index serves carries what it travels under."""
    wheel = _build_the_wheel(tmp_path / "wheelhouse")
    with zipfile.ZipFile(wheel) as archive:
        members = archive.namelist()
        metadata = next(name for name in members if name.endswith(".dist-info/METADATA"))
        declared = archive.read(metadata).decode("utf-8")
        for notice in NOTICES:
            assert f"License-File: {notice}" in declared, f"{wheel.name} declares no {notice}"
            member = next(
                (name for name in members if name.endswith(f".dist-info/licenses/{notice}")), None
            )
            assert member is not None, f"{wheel.name} carries no {notice}"
            assert archive.read(member) == (REPOSITORY / notice).read_bytes(), (
                f"{wheel.name}: the {notice} it carries is not this repository's"
            )


def test_the_notices_this_guard_compares_against_exist(tmp_path: Path) -> None:
    """ANTI-VACUITY. Two files compared byte for byte against two absent files
    would be two comparisons nobody could fail, and an empty notice reproduced
    faithfully is not a notice."""
    for notice in NOTICES:
        assert (REPOSITORY / notice).is_file(), notice
        assert (REPOSITORY / notice).read_bytes().strip(), f"{notice} is empty"
