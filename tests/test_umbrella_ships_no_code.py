# SPDX-License-Identifier: Apache-2.0
"""The umbrella is its metadata: three pins, three commands, two notices, and no module.

`sayfirst` exists so that one install yields the product. Everything the
product does is in the distributions it depends on, where it is tested and
documented. A module shipped from here would be code nobody's gate reads, under
the most visible name the project has.

Built into a directory of its own under the test's own temporary path, never
the tree's `dist/`: a guard that wrote there would make the next release's
build read what a test left behind.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
UMBRELLA = REPOSITORY / "umbrella"

#: The three commands, as the wheel's own entry-point file spells them.
ENTRY_POINTS = (
    "[console_scripts]\n"
    "sayfirst = sayfirst_cli.main:run\n"
    "sayfirst-daemon = sayfirst_quickstart.command:main\n"
    "sayfirstd = sayfirstd.main:run\n"
)


def outside_the_metadata(members: list[str]) -> list[str]:
    """Every member of a wheel that is not part of its own metadata directory."""
    return sorted(name for name in members if ".dist-info/" not in name)


def _build_the_wheel(into: Path) -> Path:
    subprocess.run(
        ("uv", "build", str(UMBRELLA), "--wheel", "--out-dir", str(into)),
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = sorted(into.glob("*.whl"))
    assert len(wheels) == 1, wheels
    return wheels[0]


def test_the_wheel_carries_its_metadata_and_nothing_else(tmp_path: Path) -> None:
    wheel = _build_the_wheel(tmp_path / "wheelhouse")
    assert wheel.name.startswith("sayfirst-"), wheel.name
    with zipfile.ZipFile(wheel) as archive:
        members = archive.namelist()
        # Anti-vacuity floor: an archive with no metadata is not a wheel that
        # ships no code, it is no wheel.
        assert any(name.endswith(".dist-info/METADATA") for name in members), members
        assert outside_the_metadata(members) == []
        entry_points = next(name for name in members if name.endswith("entry_points.txt"))
        assert archive.read(entry_points).decode("utf-8") == ENTRY_POINTS


def test_the_reading_catches_a_module_that_arrived() -> None:
    """WATCHED FIRING, on the list a wheel with one module in it would give."""
    members = ["sayfirst-1.0.0.dist-info/METADATA", "sayfirst/__init__.py"]
    assert outside_the_metadata(members) == ["sayfirst/__init__.py"]
