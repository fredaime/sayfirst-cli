# SPDX-License-Identifier: Apache-2.0
"""Article 10: the runtime a governed program holds a grant in ships in the closure.

The import sits at module level on purpose: in a reduced run (no sibling beside
this repository) the absence rule in `contract_absence.py` records this module
as not run and says so, instead of a test failing for a wheel that was never
built.
"""

from __future__ import annotations

import sayfirst_boundary


def test_the_boundary_runtime_is_importable_in_the_closure() -> None:
    assert hasattr(sayfirst_boundary, "Boundary")
