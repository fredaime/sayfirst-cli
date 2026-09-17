# SPDX-License-Identifier: Apache-2.0
"""Which tests the contract carries, established by collecting them.

`sayfirst-contract` is published on no index — article 0 forbids publishing
anything until the marks are filed — and it cannot be vendored here either
(article 14 and `docs/PROVENANCE.md`: the first copy into an open repository is
blocked by a question counsel owns). So there are machines where the contract
simply is not present: a fork's, and this project's own CI whenever the read
credential is not set.

A gate that stops dead on those machines proves nothing. A gate that runs what
it can and calls the result an ordinary pass proves less than it says it does.
Article 2 forbids the second in as many words — "an absence ... is never
rendered as a negative fact, a zero or a healthy state" — and asks a status
surface for three values where a reader might expect two.

So the tests that do not need the contract are run, and the rest are reported by
name. Which are which is **collected, never listed**: a module belongs to the
contract if importing it asks for a contract package and does not find one. A
list written here would be right on the day it was written and wrong on the day
a test grew an import, and it would be wrong silently, which is the failure this
whole file exists to avoid.

Two things the rule refuses to do, each with a test that plants the defect in
`tests/test_contract_absence.py`:

* it never hides an import failure that is not the contract's absence — a
  mistyped import, a module this repository broke, anything at all — because a
  gate that swallows those is worse than no gate;
* it never fires while the contract is installed. There, a module that cannot
  import it is a failure, and stays one.

`scripts/gate.sh` sets `SAYFIRST_GATE_NOT_RUN` to a path and reads back what was
not run, so that the count it prints comes from the collection rather than from
a second reading of it.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]

#: The import packages the contract's two distributions provide, and the only
#: names whose absence this rule reads as "the contract is absent". They are
#: named here because a distribution that is not installed cannot be asked what
#: it calls itself; the correspondence is not left to trust, though —
#: `tests/test_contract_absence.py` checks this set against the distributions'
#: own metadata on every machine where the contract *is* installed, so the two
#: cannot drift apart unnoticed.
CONTRACT_PACKAGES: frozenset[str] = frozenset(
    {"sayfirst_contract", "sayfirst_contract_stub", "sayfirst_boundary"}
)

#: The distributions that provide them: `sayfirst-contract[stub]` resolved, and
#: the boundary runtime the client depends on (article 10) — built from the same
#: sibling, so absent together in a reduced run.
CONTRACT_DISTRIBUTIONS: tuple[str, ...] = (
    "sayfirst-contract",
    "sayfirst-contract-stub",
    "sayfirst-boundary",
)

#: The environment variable the gate uses to ask for the list of what was not
#: run. Unset, nothing is written and the terminal summary is the whole report.
REPORT_VARIABLE = "SAYFIRST_GATE_NOT_RUN"


@dataclass(frozen=True)
class NotRun:
    """Something the contract's absence stopped from running, and why.

    `kind` is `module` for a test module collection could not import, and `test`
    for a single test that stood down because the contract is not installed.
    Both are checks that did not run; counting only the first would make the
    number smaller than the truth, in the direction that flatters the run.
    """

    what: str
    kind: str
    why: str


#: Filled during collection; read by the terminal summary and by the report.
NOT_RUN: list[NotRun] = []


def contract_is_installed() -> bool:
    """Whether every contract package can be found on this interpreter's path."""
    for package in sorted(CONTRACT_PACKAGES):
        try:
            found = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            return False
        if found is None:
            return False
    return True


def absent_contract_package(error: BaseException | None) -> str | None:
    """The contract package whose absence raised `error`, or `None`.

    `None` is the answer that matters, and it is the answer for everything
    except the one case: a `ModuleNotFoundError` for a contract package itself.
    A missing *sub*module of an installed contract — `sayfirst_contract.client`
    gone — is a broken contract rather than an absent one, and reads as `None`
    so that it stays a failure.

    Pytest wraps the import failure of a test module in a `CollectError` raised
    `from` it, so the chain is walked rather than the exception that arrived.
    """
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, ModuleNotFoundError) and error.name in CONTRACT_PACKAGES:
            return error.name
        error = error.__cause__ or error.__context__
    return None


def record(module_path: Path | str, package: str) -> str:
    """Record a module that was not run, and return the sentence that says why."""
    module = _relative(module_path)
    why = f"it imports {package}"
    NOT_RUN.append(NotRun(module, "module", why))
    return f"the contract is absent: {module} {why[len('it ') :]}"


def skip_without_the_contract(request, why: str) -> None:
    """Stand this test down because the contract is not installed, and be counted.

    A test that can only run against an installed contract is as much a check
    the contract's absence cost as a module that would not import, and the gate
    counts it as one. `pytest.skip` alone would leave it out of the count and
    make the reduced run look like it proved more than it did.
    """
    NOT_RUN.append(NotRun(request.node.nodeid, "test", why))
    pytest.skip(f"the contract is absent: {why}")


def write_report(destination: str | None = None) -> Path | None:
    """Write what was not run where the gate asked for it, one module a line.

    The file is written even when it is empty: "nothing was skipped" and "the
    run never got this far" are different facts, and the gate reads the
    difference.
    """
    destination = os.environ.get(REPORT_VARIABLE) if destination is None else destination
    if not destination:
        return None
    path = Path(destination)
    path.write_text(
        "".join(f"{item.kind}\t{item.what}\t{item.why}\n" for item in NOT_RUN), encoding="utf-8"
    )
    return path


def _relative(path: Path | str) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(REPOSITORY))
    except ValueError:
        return str(resolved)


class ContractAwareModule(pytest.Module):
    """A test module that says the contract is absent instead of erroring out."""

    def collect(self):  # type: ignore[no-untyped-def]
        try:
            return super().collect()
        except Exception as error:
            if contract_is_installed():
                raise
            package = absent_contract_package(error)
            if package is None:
                raise
            pytest.skip(record(self.path, package), allow_module_level=True)
