# SPDX-License-Identifier: Apache-2.0
"""Article 15: every file this project authors names its licence in its own bytes.

"Every file the project authors — source and documentation alike, the
licence text and the NOTICE excepted, being notices rather than works —
carries an SPDX identifier naming its licence."  — article 15
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]

#: Notices rather than works, which article 15 excepts by name.
EXCEPTED = frozenset({"LICENSE", "NOTICE", ".gitignore"})

#: The licences a file of this repository may name (article 15).
PERMITTED = ("Apache-2.0", "Apache-2.0 OR MIT-0")


def _tracked() -> list[Path]:
    listed = subprocess.run(
        ("git", "ls-files", "-z"), cwd=REPOSITORY, capture_output=True, text=True, check=True
    ).stdout
    return [Path(name) for name in listed.split("\0") if name]


def _identifier(text: str) -> str | None:
    marker = "SPDX-License" + "-Identifier:"
    closer = "-" + "->"
    for line in text.splitlines()[:5]:
        if marker in line:
            stated = line.split(marker, 1)[1].strip()
            return stated.removesuffix(closer).strip()
    return None


def test_every_authored_file_carries_an_spdx_identifier() -> None:
    """Article 15: the file-level expression governs the file."""
    assert shutil.which("git") is not None
    tracked = _tracked()
    # Anti-vacuity floor: an enumeration that found nothing cannot pass.
    assert len(tracked) >= 10, tracked
    missing = []
    wrong = []
    for item in tracked:
        if item.name in EXCEPTED:
            continue
        text = (REPOSITORY / item).read_text(encoding="utf-8")
        identifier = _identifier(text)
        if identifier is None:
            missing.append(item)
        elif identifier not in PERMITTED:
            wrong.append((item, identifier))
    assert missing == []
    assert wrong == []


def test_the_guard_catches_a_file_without_one(tmp_path: Path) -> None:
    """A reader of the header, proven against a file that has none."""
    assert _identifier("print('hello')\n") is None
    assert _identifier("# SPDX-License" + "-Identifier: Apache-2.0\n") == "Apache-2.0"
    assert _identifier("<!-- SPDX-License" + "-Identifier: Apache-2.0 -->\n") == "Apache-2.0"
