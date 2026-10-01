# SPDX-License-Identifier: Apache-2.0
"""Article 15: the second distribution this repository publishes reproduces the notices too.

The client's wheel finds the licence and the notice beside its project file.
The umbrella's project file lives one directory down, where neither is, so both
are carried in by hand: into the source distribution by its build configuration,
and into the wheel by `umbrella/hatch_build.py`. A thing carried by hand is a
thing that can be dropped by hand, so it is held here the way the client's own
is held: the metadata DECLARES the files, the archive CARRIES them, and the
bytes are this repository's.

Built the way a release builds it — the source distribution, and the wheel made
from it — so the artefact read here is the artefact a tag publishes.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
UMBRELLA = REPOSITORY / "umbrella"

#: The notices every redistribution of this repository carries.
NOTICES = ("LICENSE", "NOTICE")


def _build_both(into: Path) -> tuple[Path, Path]:
    """The umbrella's source distribution, and the wheel made from it."""
    subprocess.run(
        ("uv", "build", str(UMBRELLA), "--out-dir", str(into)),
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


def test_the_umbrella_declares_and_carries_the_repository_notices(tmp_path: Path) -> None:
    sdist, wheel = _build_both(tmp_path / "dist")
    with tarfile.open(sdist) as archive:
        roots = {Path(name).name for name in archive.getnames() if len(Path(name).parts) == 2}
        for notice in NOTICES:
            assert notice in roots, f"{sdist.name} carries no {notice} at its root"
            member = archive.extractfile(
                next(name for name in archive.getnames() if Path(name).name == notice)
            )
            assert member is not None
            assert member.read() == (REPOSITORY / notice).read_bytes(), f"{sdist.name}: {notice}"
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


def test_a_wheel_built_straight_from_the_tree_carries_them_too(tmp_path: Path) -> None:
    """The gate's install check builds the wheel this way, without a source distribution."""
    subprocess.run(
        ("uv", "build", str(UMBRELLA), "--wheel", "--out-dir", str(tmp_path)),
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )
    (wheel,) = sorted(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        for notice in NOTICES:
            member = next(
                name
                for name in archive.namelist()
                if name.endswith(f".dist-info/licenses/{notice}")
            )
            assert archive.read(member) == (REPOSITORY / notice).read_bytes(), notice
