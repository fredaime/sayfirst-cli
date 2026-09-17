# SPDX-License-Identifier: Apache-2.0
"""Article 15: a redistribution nobody can build carries no notice at all.

`uv build` makes the wheel FROM the source distribution, so the licence and the
notice have to travel in the source distribution too: once the tree is unpacked
there is no repository root above the project to reach for, and a build that
reached for one would find nothing. This repository carries them across by
naming them in the project file rather than by a default, and this is what reads
that back out of the artefact instead of out of the declaration.

The whole round trip is one `uv build`, which is how the release workflow builds
too: the source distribution is made from the tree, and the wheel is made from
the source distribution. So a wheel that carries the notices here proves the
crossing, and not merely the tree.

Built into the test's own temporary path, never the tree's `dist/`. One rule per
file, as the control plane's twin guard is.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

#: The notices every redistribution of this repository carries, at its root.
NOTICES = ("LICENSE", "NOTICE")


def _build_both(into: Path) -> tuple[Path, Path]:
    """The source distribution this tree makes, and the wheel made from it."""
    subprocess.run(
        ("uv", "build", "--out-dir", str(into)),
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )
    sdists = sorted(into.glob("*.tar.gz"))
    wheels = sorted(into.glob("*.whl"))
    assert len(sdists) == 1, sdists
    assert len(wheels) == 1, wheels
    return sdists[0], wheels[0]


def test_the_notices_survive_the_round_trip_through_the_source_distribution(
    tmp_path: Path,
) -> None:
    """Article 15: the notices are in the artefact a fork rebuilds from."""
    sdist, wheel = _build_both(tmp_path / "dist")
    with tarfile.open(sdist) as archive:
        # At the root of the unpacked tree, which is where a build looks for
        # them: `<name>-<version>/LICENSE`, and never two directories deeper.
        roots = {Path(name).name for name in archive.getnames() if len(Path(name).parts) == 2}
        for notice in NOTICES:
            assert notice in roots, f"{sdist.name} carries no {notice} at its root"
            member = archive.extractfile(
                next(name for name in archive.getnames() if Path(name).name == notice)
            )
            assert member is not None
            assert member.read() == (REPOSITORY / notice).read_bytes(), f"{sdist.name}: {notice}"
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        for notice in NOTICES:
            member = next((name for name in names if name.endswith(f"licenses/{notice}")), None)
            assert member is not None, f"{wheel.name} carries no {notice}"
            assert archive.read(member) == (REPOSITORY / notice).read_bytes(), (
                f"{wheel.name}: {notice}"
            )
