# SPDX-License-Identifier: Apache-2.0
"""Make `scripts/` importable, so a guard is tested where it is run from.

The dependency-closure guard is a script because it installs things; its rules
are ordinary functions, and the tests read them from the same file the gate
executes. Two copies of one rule is how a gate and its test stop agreeing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_here = Path(__file__).resolve().parent
# `scripts/` so a guard is read from the same file the gate executes, and this
# directory so the test doubles beside these tests import by their own names.
sys.path.insert(0, str(_here.parent / "scripts"))
sys.path.insert(0, str(_here))

# Every import below is inside a fixture on purpose. This file is collected on
# machines where the contract is not installed, and `contract_absence.py` reads
# that absence off the *test modules* that could not import it; a conftest that
# imported the contract itself would stop the run instead of reducing it.


@pytest.fixture
def no_socket(monkeypatch):
    """Forbid every connection for the length of one test.

    An offline check that opened a socket would still pass its assertions while
    proving the opposite of what it claims, so the connection is not merely
    unused here — it fails the test.
    """
    from sayfirst_cli import reads

    def forbidden(*args, **kwargs):
        pytest.fail("this invocation must not open a connection")

    monkeypatch.setattr(reads, "connect", forbidden)


@pytest.fixture
def record():
    """One recorded decision, as the daemon renders it."""
    from documents import decision_record

    return decision_record()


@pytest.fixture
def entries():
    """The entries of a published bundle: a chain the contract's verifier accepts."""
    from documents import vector_entries

    return vector_entries()


def pytest_pycollect_makemodule(module_path, parent):  # type: ignore[no-untyped-def]
    """Collect every test module as one that knows what an absent contract means.

    The rule itself is in `contract_absence.py`, which the tests read too; the
    import is here rather than at the top of this file because the directory
    that makes it importable is added above.
    """
    from contract_absence import ContractAwareModule

    return ContractAwareModule.from_parent(parent, path=module_path)


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    """Leave the list of what was not run where `scripts/gate.sh` asked for it."""
    from contract_absence import write_report

    write_report()


def pytest_terminal_summary(terminalreporter) -> None:  # type: ignore[no-untyped-def]
    """Say what the contract's absence cost this run, by name and by count.

    A run that skipped four modules and printed "passed" would be article 2's
    absence rendered as a healthy state, whoever was reading it.
    """
    from contract_absence import NOT_RUN

    if not NOT_RUN:
        return
    terminalreporter.write_sep("=", "the contract is absent", yellow=True)
    for item in sorted(NOT_RUN, key=lambda entry: (entry.kind, entry.what)):
        terminalreporter.write_line(f"  not run: {item.what} — {item.why}")
    terminalreporter.write_line(
        f"{len(NOT_RUN)} checks were not run. This run proves less than a run with the "
        f"contract installed; `scripts/gate.sh` says what would install it."
    )
