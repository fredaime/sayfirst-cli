# SPDX-License-Identifier: Apache-2.0
"""No shipped-pack suite keeps a boundary double of its own.

The rule, rather than the doubles: `tests/pack_doubles.py` holds them and says
what three copies cost. This file is what stops a fourth copy arriving quietly
in the next pack's suite — the failure mode was not a wrong double but a
CORRECTED one, made in two of the three files, with the third testing the old
behaviour and a green run saying nothing about it.

Read as source rather than imported, so that the answer does not depend on which
module the name happens to be bound in at run time — and so this file needs no
contract package to say it, which means a reduced run still says it.
"""

from __future__ import annotations

import ast
from pathlib import Path

#: The doubles that were copied. `Spy` is included even though the three copies
#: differed: the differences were a guarded call and two docstrings, and the
#: shared one is their union.
SHARED = frozenset({"Handle", "FakeBoundary", "RefusingBoundary", "Spy"})

TESTS = Path(__file__).resolve().parent
DOUBLES = TESTS / "pack_doubles.py"


def _classes(path: Path) -> set[str]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in module.body if isinstance(node, ast.ClassDef)}


def test_the_shipped_pack_suites_keep_no_boundary_double_of_their_own() -> None:
    suites = sorted(TESTS.glob("test_*_pack.py"))
    # Anti-vacuity: a glob that matched nothing would pass every assertion below.
    assert len(suites) >= 3, suites
    for path in suites:
        defined = _classes(path) & SHARED
        assert not defined, (
            f"{path.name} defines its own {sorted(defined)}; `pack_doubles` holds them"
        )


def test_the_shared_module_defines_every_one_of_them() -> None:
    """The other half of the rule: the suites may not keep one, so this must have it."""
    assert _classes(DOUBLES) >= SHARED, sorted(SHARED - _classes(DOUBLES))


def test_the_shared_module_says_what_the_duplication_cost() -> None:
    """A helper extracted without the reason is a helper somebody inlines again."""
    docstring = ast.get_docstring(ast.parse(DOUBLES.read_text(encoding="utf-8")))
    assert docstring is not None
    assert "cost" in docstring
