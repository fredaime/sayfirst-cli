# SPDX-License-Identifier: Apache-2.0
"""The rule that decides which tests the contract carries, held to its two edges.

`tests/contract_absence.py` lets a run continue on a machine where
`sayfirst-contract` is not installed, reporting by name the modules it could not
import. That is a mechanism for *not running tests*, so it is the last mechanism
in this repository that may be trusted on its description. Every claim it makes
is planted against here:

* the modules it does not run are the ones collection could not import, and it
  is collection that decides — the set is read off a real `pytest` run, not off
  a list in a file;
* a run it lets through still runs tests, and a run with the contract installed
  runs strictly more of them;
* an import failure that is not the contract's absence stays a failure;
* the packages the rule names are the packages the contract's own distributions
  provide.
"""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import pytest
from contract_absence import (
    CONTRACT_DISTRIBUTIONS,
    CONTRACT_PACKAGES,
    absent_contract_package,
    contract_is_installed,
    skip_without_the_contract,
    write_report,
)

REPOSITORY = Path(__file__).resolve().parents[1]

#: A `sitecustomize` that makes named top-level packages unimportable to a child
#: interpreter, the way an uninstalled distribution is: the import machinery is
#: asked first and answers with the `ModuleNotFoundError` a real absence gives,
#: carrying the same `name`. Hiding a package is how this file arranges an
#: absence without uninstalling anything from the environment it is running in.
_HIDER = """\
import os
import sys
from importlib.abc import MetaPathFinder


class _Absent(MetaPathFinder):
    def __init__(self, names):
        self.names = names

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split(".")[0]
        if top in self.names:
            raise ModuleNotFoundError(f"No module named {top!r}", name=top)
        return None


hidden = {name for name in os.environ.get("SAYFIRST_TEST_HIDE", "").split(",") if name}
if hidden:
    sys.meta_path.insert(0, _Absent(hidden))
"""


class Collected:
    """What one child `pytest --collect-only` run collected, and what it did not."""

    def __init__(self, completed: subprocess.CompletedProcess[str], report: Path) -> None:
        self.completed = completed
        self.output = completed.stdout + completed.stderr
        self.tests = [line for line in completed.stdout.splitlines() if "::" in line]
        self.not_run = [
            line.split("\t") for line in report.read_text(encoding="utf-8").splitlines() if line
        ]
        self.modules = {what: why for kind, what, why in self.not_run if kind == "module"}


def collect(tmp_path: Path, hide: tuple[str, ...] = ()) -> Collected:
    """Collect this repository's tests in a child interpreter, hiding what is named."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    hider = tmp_path / "sitecustomize.py"
    hider.write_text(_HIDER, encoding="utf-8")
    report = tmp_path / "not-run"
    report.write_text("", encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), *([environment["PYTHONPATH"]] if environment.get("PYTHONPATH") else [])]
    )
    environment["SAYFIRST_TEST_HIDE"] = ",".join(hide)
    environment["SAYFIRST_GATE_NOT_RUN"] = str(report)
    completed = subprocess.run(
        (sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "no:cacheprovider"),
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return Collected(completed, report)


def test_the_modules_the_contract_carries_are_the_ones_collection_could_not_import(
    tmp_path: Path,
) -> None:
    """The set comes off a real run: hide the contract, and read what was skipped."""
    run = collect(tmp_path, hide=tuple(sorted(CONTRACT_PACKAGES)))

    assert run.completed.returncode == 0, run.output
    assert run.modules, "the contract was hidden and no module said it needed it"
    for module, why in run.modules.items():
        assert (REPOSITORY / module).is_file(), module
        assert why.removeprefix("it imports ") in CONTRACT_PACKAGES, why
    # Anti-vacuity: a rule that skipped everything would satisfy the lines above
    # and prove nothing at all.
    assert run.tests, "the contract was hidden and nothing was left to run"


def test_the_contract_installed_skips_nothing_and_collects_strictly_more(
    request, tmp_path: Path
) -> None:
    """The modules it skips do hold tests, and the rule stands down when it must."""
    if not contract_is_installed():
        skip_without_the_contract(request, "this comparison needs a run with it and one without")

    absent = collect(tmp_path / "hidden", hide=tuple(sorted(CONTRACT_PACKAGES)))
    present = collect(tmp_path / "present")

    assert present.completed.returncode == 0, present.output
    assert present.not_run == []
    assert len(present.tests) > len(absent.tests)


def test_an_import_failure_that_is_not_the_contract_stays_a_failure(tmp_path: Path) -> None:
    """The planted defect: hide the client itself, and the run must go red.

    A mechanism that turns "this module would not import" into "not run" is one
    typo away from turning a broken repository into a quiet green. So the rule
    is asked about a module it must not recognise, and the child run has to
    fail, naming what was missing.
    """
    run = collect(tmp_path, hide=("sayfirst_cli",))

    assert run.completed.returncode != 0, run.output
    assert "sayfirst_cli" in run.output
    assert not [entry for entry in run.not_run if "sayfirst_cli" in entry[1]]


def test_a_missing_submodule_of_an_installed_contract_is_not_an_absent_contract() -> None:
    """A broken contract is not an absent one, and only the second is excusable."""
    submodule = ModuleNotFoundError("x", name="sayfirst_contract.client")
    neighbour = ModuleNotFoundError("x", name="sayfirst_contractor")
    assert absent_contract_package(submodule) is None
    assert absent_contract_package(neighbour) is None
    assert absent_contract_package(ImportError("cannot import name 'Answered'")) is None
    assert absent_contract_package(None) is None


def test_the_rule_reads_the_cause_pytest_wraps_the_import_failure_in() -> None:
    """Pytest raises `CollectError` *from* the `ImportError`; the chain is walked."""
    cause = ModuleNotFoundError("No module named 'sayfirst_contract'", name="sayfirst_contract")
    try:
        try:
            raise cause
        except ModuleNotFoundError as error:
            raise RuntimeError("ImportError while importing test module") from error
    except RuntimeError as wrapper:
        assert absent_contract_package(wrapper) == "sayfirst_contract"


def test_the_packages_the_rule_names_are_the_ones_the_contract_provides(request) -> None:
    """Named by hand because an absent distribution cannot be asked; checked here."""
    provided: set[str] = set()
    for name in CONTRACT_DISTRIBUTIONS:
        try:
            found = _top_level_packages(name)
        except PackageNotFoundError:
            skip_without_the_contract(request, f"{name} is not installed, so it cannot be asked")
        assert found, f"{name} is installed and provides no top-level package"
        provided |= found
    assert provided == set(CONTRACT_PACKAGES)


def test_an_unasked_report_is_not_written(tmp_path: Path) -> None:
    """The gate asks for the list by naming a path; nothing else writes a file."""
    assert write_report("") is None
    written = write_report(str(tmp_path / "asked"))
    assert written is not None and written.exists()


def _top_level_packages(name: str) -> set[str]:
    """The top-level import packages a distribution installs, read from its own files."""
    installed = distribution(name)
    declared = installed.read_text("top_level.txt")
    if declared:
        return {line.strip() for line in declared.splitlines() if line.strip()}
    return {
        file.parts[0]
        for file in installed.files or ()
        if len(file.parts) > 1
        and file.parts[-1].endswith(".py")
        and not file.parts[0].endswith((".dist-info", ".data"))
    }


def test_a_test_that_stands_down_for_the_contract_is_counted_too(request) -> None:
    """A skip left out of the count would shrink the number that matters.

    The planted entry is removed again: this test runs inside the very run whose
    count it is checking, and a count with a plant in it is the defect twice.
    """
    from contract_absence import NOT_RUN

    before = len(NOT_RUN)
    with pytest.raises(pytest.skip.Exception):
        skip_without_the_contract(request, "planted")
    try:
        assert len(NOT_RUN) == before + 1
        assert NOT_RUN[-1].kind == "test"
        assert NOT_RUN[-1].why == "planted"
        assert NOT_RUN[-1].what.endswith(
            "test_a_test_that_stands_down_for_the_contract_is_counted_too"
        )
    finally:
        del NOT_RUN[before:]
