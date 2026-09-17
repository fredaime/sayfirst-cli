# SPDX-License-Identifier: Apache-2.0
"""Which tests the contract carries, established by watching them ask for it.

`sayfirst-contract` is published on no index — article 0 forbids publishing
anything until the marks are filed — and it cannot be vendored here either
(article 14 and `docs/PROVENANCE.md`: the first copy into an open repository is
blocked by a question counsel owns). So there are machines where the contract
simply is not present: a fork with no network, a runner behind a proxy, anyone
working offline.

A gate that stops dead on those machines proves nothing. A gate that runs what
it can and calls the result an ordinary pass proves less than it says it does.
Article 2 forbids the second in as many words — "an absence ... is never
rendered as a negative fact, a zero or a healthy state" — and asks a status
surface for three values where a reader might expect two.

So the tests that do not need the contract are run, and the rest are reported by
name. Which are which is **collected, never listed**: a test belongs to the
contract if asking for a contract package is what stopped it. A list written
here would be right on the day it was written and wrong on the day a test grew
an import, and it would be wrong silently, which is the failure this whole file
exists to avoid.

**There are two moments at which a test asks, and reading only the first cost a
red run.** A module that imports the contract at its top says so during
collection, and `ContractAwareModule` below stands that module down. A module
that imports only `sayfirst_cli.main` says nothing during collection and asks
later: a verb is resolved through `importlib` when it is dispatched, so
`ask --help` reaches for the contract at CALL time, inside a module that
collected cleanly. Those tests failed while every module-level importer was
politely skipped — the same fact about the world, rendered once as a stand-down
and once as a crash. `record_at_call_time` is the second reading, and it is the
same rule: the failure is read, never a list of tests.

Two things the rule refuses to do at either moment, each with a test that plants
the defect in `tests/test_contract_absence.py`:

* it never hides an import failure that is not the contract's absence — a
  mistyped import, a module this repository broke, anything at all — because a
  gate that swallows those is worse than no gate;
* it never fires while the contract is installed. There, a test that cannot
  import it is a failure, and stays one.

`scripts/gate.sh` sets `SAYFIRST_GATE_NOT_RUN` to a path and reads back what was
not run, so that the count it prints comes from the run rather than from a second
reading of it.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from contextlib import contextmanager
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


def record_at_call_time(node_id: str, error: BaseException) -> str | None:
    """Record a test the contract's absence stopped mid-run, or answer `None`.

    Collection reads the modules that import the contract at their top. This
    reads the ones that ask for it later — a test that drives a command, which
    this client imports only when the verb is dispatched — and it reads it off
    the failure that arrived rather than off a list of tests, for the reason the
    module docstring gives.

    `None` is the answer that keeps the gate a gate, and it is the answer in
    both of the cases the rule refuses: a failure that is not a contract
    package's absence, and any failure at all while the contract is installed.
    The caller re-raises on `None`, so a red test stays red.
    """
    if contract_is_installed():
        return None
    package = absent_contract_package(error)
    if package is None:
        return None
    why = f"it imports {package} when it runs"
    NOT_RUN.append(NotRun(node_id, "test", why))
    return f"the contract is absent: {node_id} {why[len('it ') :]}"


@contextmanager
def standing_down_what_the_contract_stopped(node_id: str) -> Iterator[None]:
    """Run a phase of one test, standing it down if the contract's absence stops it.

    The context manager lives here rather than in `tests/conftest.py` because
    this is the file the tests read: a rule for *not running tests* that was
    written in one place and held in another is the drift this project keeps
    finding. `conftest.py` wraps the setup and the call phases with it and does
    nothing else.
    """
    try:
        yield
    except BaseException as error:
        sentence = record_at_call_time(node_id, error)
        if sentence is None:
            raise
        pytest.skip(sentence)


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
