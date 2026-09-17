# SPDX-License-Identifier: Apache-2.0
"""Running this package as a module does something, or says it cannot.

The published entry point is the console script, which resolves to
`sayfirst_cli.main:run`. But `python -m sayfirst_cli.main` is a thing people
type, and until 2026-09-14 it did the worst possible thing: it imported the
module, ran nothing, printed nothing, and **exited 0**.

A command that reports success while doing nothing is the false all-clear
article 2 forbids, and it is worse here than in most places — this is the
client of a governance system, so "it exited 0" is exactly the reading a
caller must never be given for an act that did not happen. It was found by an
end-to-end walk in the control plane's repository that invoked the client this
way and got a green result from a command that had not run.

The fix is one `__main__` guard. This test is what stops it being deleted as
dead weight by someone who has not met the failure.

**And `--help` is asked here without the control plane's contract
distribution.** The dispatch used to import every subcommand at import time, so
the form above ended in a `ModuleNotFoundError` traceback wherever the contract
is absent — and three tests of this file then FAILED in a reduced run instead of
standing down and being counted, which is article 2's rule about an absence
inverted: the absence rendered as a defect. `--help` is a claim about what this
tool answers and it needs none of the contract, so it is asked in an interpreter
that refuses those imports and is required to answer anyway.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from contract_absence import CONTRACT_PACKAGES, contract_is_installed, skip_without_the_contract

REPOSITORY = Path(__file__).resolve().parents[1]

#: An interpreter in which the contract simply is not there, whatever this
#: machine has installed. The absence is arranged rather than waited for: the
#: gate's own environment HAS the contract, and a claim about a machine without
#: one is worth nothing if it can only be checked on a machine without one. The
#: refusal is the interpreter's own `ModuleNotFoundError`, named for the package
#: that was asked for, which is exactly what an absent distribution raises.
_WITHOUT_THE_CONTRACT = f"""\
import runpy
import sys


class Absent:
    packages = {sorted(CONTRACT_PACKAGES)!r}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in self.packages:
            raise ModuleNotFoundError(f"No module named {{fullname!r}}", name=fullname)
        return None


sys.meta_path.insert(0, Absent())
runpy.run_module("sayfirst_cli.main", run_name="__main__")
"""


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "sayfirst_cli.main", *arguments],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _run_without_the_contract(*arguments: str) -> subprocess.CompletedProcess[str]:
    """The same dispatch, in an interpreter where no contract package can be found."""
    return subprocess.run(
        [sys.executable, "-c", _WITHOUT_THE_CONTRACT, *arguments],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_running_the_module_with_no_command_refuses_rather_than_succeeding() -> None:
    finished = _run()
    assert finished.returncode != 0, (
        "the module ran as a program, did nothing, and reported success: "
        f"stdout={finished.stdout!r} stderr={finished.stderr!r}"
    )
    assert finished.stderr, "it refused without saying anything"


def test_the_refusal_names_the_command_the_caller_omitted() -> None:
    """Silence and an unexplained non-zero are both unhelpful; this says which."""
    finished = _run()
    assert "command" in finished.stderr, finished.stderr
    assert "ask" in finished.stderr, "the usage does not name the command that exists"


def test_the_dispatch_names_every_command_with_no_contract_installed() -> None:
    """A reduced gate must COUNT what it did not run, never fail on it.

    `--help` is a claim about what this tool answers, and the dispatch is where
    that claim is kept — so it is asked here of an interpreter that can find no
    contract package at all, and required to answer 0 with every subcommand
    named. Before the dispatch became lazy this was a `ModuleNotFoundError`
    traceback, and this file's tests were three failures in a reduced run rather
    than three checks that stood down and were counted.
    """
    finished = _run_without_the_contract("--help")
    assert finished.returncode == 0, finished.stderr
    assert "Traceback" not in finished.stderr
    for command in ("ask", "trace", "explain", "evidence", "approvals", "instrument", "packs"):
        assert command in finished.stdout


def test_the_absence_this_file_arranges_is_the_one_the_gate_reports() -> None:
    """Anti-vacuity: the blocker above really does hide the contract.

    Without this, a blocker that silently found nothing to block would make the
    test above a claim about the ordinary environment — which is the environment
    it exists to be independent of.
    """
    if not contract_is_installed():
        return
    finished = subprocess.run(
        [sys.executable, "-c", "import sys\nsys.exit(0)"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert finished.returncode == 0
    blocked = subprocess.run(
        [
            sys.executable,
            "-c",
            _WITHOUT_THE_CONTRACT.replace(
                'runpy.run_module("sayfirst_cli.main", run_name="__main__")',
                "import sayfirst_contract",
            ),
        ],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert blocked.returncode != 0
    assert "No module named 'sayfirst_contract'" in blocked.stderr


def test_running_the_module_reaches_the_real_entry_point(request) -> None:
    """`--help` for a real subcommand proves the dispatch was entered.

    Its `--help` half moved to the test above, which needs no contract. What is
    left needs one — `ask` builds the contract's own parser — so it stands down
    through the rule that COUNTS it rather than failing.
    """
    if not contract_is_installed():
        skip_without_the_contract(request, "`ask --help` builds the contract's own parser")
    finished = _run("ask", "--help")
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert "--capability" in finished.stdout
    assert "--socket" in finished.stdout
