#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# The whole gate of this repository, in one command. What it runs is what CI
# runs; there is no step that exists only on a machine.
#
#   format   ruff format --check      every authored file is formatted
#   lint     ruff check               the lint rules the workspace selects
#   tests    pytest                   including the guards under tests/
#   closure  scripts/check_dependency_closure.py
#                                     articles 13 and 14, measured on a real
#                                     install, and proving on every run that it
#                                     can fail
#
# The contract this client pins is built from source, never taken from an index:
# the version a change pins may not be on one yet (it is published with the
# release that pins it), and a gate that read the index would prove this client
# against whatever the index held. So this gate is told where a checkout of the
# control plane repository is, and it builds the contract from a named ref of
# it rather than from whatever that clone has checked out.
#
#   SAYFIRST_CONTRACT_SOURCE   default ../sf-control-plane-lt
#   SAYFIRST_CONTRACT_REF      default origin/main
#   SAYFIRST_PYTHON            default 3.13
#
# The contract is built from that checkout and cannot be vendored here either
# (article 14 and `docs/PROVENANCE.md`), so on some machines — a fork with no
# network, a runner behind a proxy, anyone offline — it is simply not there.
# This gate does not treat that as a crash, and does not treat it as a pass. It has three
# outcomes rather than two, which is article 2's rule about status surfaces
# applied to the gate's own status:
#
#   0            full green. Everything above ran.
#   75           reduced green. The contract is absent. Format, lint and every
#                test that could run without it ran and passed; every check that
#                could not is named, counted and printed. A reduced run is not a
#                pass and never renders as one.
#   any other    failure. Something the gate ran said no — including a reduced
#                run whose environment turned out to hold the contract after all.
#
# What a reduced run does not prove: nothing about the contract, its generation
# marker or its golden scenarios; nothing about the installed dependency closure
# of articles 13 and 14, whose guard installs the contract in order to measure
# it; and — as of this writing, and readable in the list the run prints rather
# than promised here — nothing about this client against a daemon, because the
# tests that start one are among the ones it could not run. It proves that the
# source is formatted, that it lints, and that the guards reading only this
# repository's own files still hold.
#
# Which tests need the contract is decided by watching them ask for it, never by
# a list here: `tests/contract_absence.py` holds the rule, this script reads back
# what it stood down through SAYFIRST_GATE_NOT_RUN, and
# `tests/test_contract_absence.py` plants the defects against it. A test can ask
# at either of two moments — when its module is imported, and when it runs, since
# this client imports a command only when the verb is dispatched — and the rule
# reads both. Reading only the first is what made this gate fail on a machine
# with no contract instead of reducing on it.
set -euo pipefail

#: Two of the three outcomes have a status of their own; the third is every
#: other status there is. `tests/test_gate_modes.py` reads these two lines and
#: requires the workflow to render all three differently.
readonly GATE_FULL_GREEN=0
readonly GATE_REDUCED_GREEN=75

# 75 is EX_TEMPFAIL: a status no tool this gate runs produces, so it cannot be
# forged by a failure. If one ever does produce it, it is reported as the
# failure it is rather than as a reduced pass.
on_failure() {
  status=$?
  trap - ERR
  if [ "$status" -eq "$GATE_REDUCED_GREEN" ]; then
    echo "gate: a check exited $GATE_REDUCED_GREEN, which is reserved for a reduced run" >&2
    status=1
  fi
  exit "$status"
}
trap on_failure ERR

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository"

contract_source="${SAYFIRST_CONTRACT_SOURCE:-$repository/../sf-control-plane-lt}"
contract_ref="${SAYFIRST_CONTRACT_REF:-origin/main}"
python_version="${SAYFIRST_PYTHON:-3.13}"
wheelhouse="$repository/.wheelhouse"
materialised="$wheelhouse/contract-source"
not_run="$wheelhouse/not-run"

if [ -d "$contract_source" ]; then
  mode=full
  venv="$repository/.venv"
else
  mode=reduced
  # An environment of its own. A reduced run that borrowed the contract a full
  # run left in .venv would prove more than it says here and less than it says
  # on a machine that never had one. Separation is not enough on its own, so it
  # is measured below rather than assumed.
  venv="$repository/.venv-reduced"
  echo "gate: no checkout of the control plane repository at $contract_source"
  echo "gate: the contract is built from that source and is not vendored here"
  echo "gate: (article 14), so this run is reduced. Set SAYFIRST_CONTRACT_SOURCE"
  echo "gate: to a checkout of that repository for the full gate."
fi

mkdir -p "$wheelhouse"

if [ "$mode" = full ]; then
  rm -rf "$materialised"
  mkdir -p "$materialised"
  if [ -d "$contract_source/.git" ]; then
    echo "gate: reading $contract_source at $contract_ref ($(git -C "$contract_source" rev-parse "$contract_ref"))"
    git -C "$contract_source" archive "$contract_ref" | tar -x -C "$materialised"
  else
    echo "gate: reading $contract_source as a plain directory"
    cp -a "$contract_source/." "$materialised/"
  fi

  echo "gate: building the contract, its optional fake, and the boundary runtime"
  uv build --project "$materialised" --package sayfirst-contract --wheel -o "$wheelhouse" >/dev/null
  uv build --project "$materialised" --package sayfirst-contract-stub --wheel -o "$wheelhouse" >/dev/null
  uv build --project "$materialised" --package sayfirst-boundary --wheel -o "$wheelhouse" >/dev/null
fi

echo "gate: preparing the development environment ($mode)"
uv venv --allow-existing --python "$python_version" "$venv" >/dev/null
python="$venv/bin/python"
if [ "$mode" = full ]; then
  # The pin is READ from pyproject.toml, never spelled here a second time (two
  # copies of one rule is how a gate and its project stop agreeing). And the
  # freshly built wheel is installed with --reinstall: the sibling can change
  # without changing its version, and an installer that saw the same version
  # already present left the OLD contract in place — measured 2026-09-15, 37
  # tests red against a transport the archive plainly carried.
  contract_pin="$("$python" -c 'import tomllib; d = tomllib.load(open("pyproject.toml", "rb")); print(next(x for x in d["dependency-groups"]["dev"] if x.startswith("sayfirst-contract[stub]")))')"
  # Read the same way as the stub pin above, from `dependencies` rather than
  # the dev group: the boundary is a runtime dependency of the client, not a
  # test-only one, and its pin is not spelled a second time here.
  boundary_pin="$("$python" -c 'import tomllib; d = tomllib.load(open("pyproject.toml", "rb")); print(next(x for x in d["project"]["dependencies"] if x.startswith("sayfirst-boundary")))')"
  uv pip install --quiet --python "$python" --reinstall \
    --no-index --find-links "$wheelhouse" \
    "$contract_pin" "$boundary_pin"
fi
uv pip install --quiet --python "$python" pytest==8.4.1 ruff==0.12.12
uv pip install --quiet --python "$python" --no-deps --editable "$repository"

# Asked of the same rule the tests use, rather than of a second reading of it
# written here: two copies of one rule is how a gate and its tests stop agreeing.
if [ "$mode" = reduced ] && "$python" -c 'import sys
sys.path.insert(0, "tests")
from contract_absence import contract_is_installed
sys.exit(0 if contract_is_installed() else 1)'; then
  echo "gate: the contract is importable in the reduced environment at $venv." >&2
  echo "gate: a reduced run must not borrow it; this run would prove more than it says." >&2
  echo "gate: remove that directory and run again." >&2
  exit 1
fi

echo "== format =="
"$python" -m ruff format --check .
echo "== lint =="
"$python" -m ruff check .
echo "== tests =="
rm -f "$not_run"
# -rs reports every skip with its reason, so a test that stood down is read
# rather than counted as a dot. The control plane's own workflow does the same,
# for the same reason: "held" and "not runnable" are different outcomes.
SAYFIRST_GATE_NOT_RUN="$not_run" "$python" -m pytest -q -rs

if [ ! -f "$not_run" ]; then
  echo "gate: the test run left no record of what it did not run at $not_run" >&2
  echo "gate: tests/contract_absence.py owns that record; the gate will not guess." >&2
  exit 1
fi
checks_not_run="$(grep -c . "$not_run" || true)"
modules_not_run="$(grep -c '^module	' "$not_run" || true)"
modules_present="$(find tests -name 'test_*.py' | wc -l | tr -d ' ')"
modules_run=$((modules_present - modules_not_run))

if [ "$mode" = full ]; then
  if [ "$checks_not_run" -ne 0 ]; then
    echo "gate: the contract was built and installed and $checks_not_run checks still stood" >&2
    echo "gate: down for its absence. That is a failure, not a reduced run:" >&2
    sed 's/^/gate:   /' "$not_run" >&2
    exit 1
  fi
  echo "== closure (articles 13 and 14) =="
  "$python" scripts/check_dependency_closure.py \
    --contract-source "$materialised" --python "$python_version"
  echo "gate: full green — format, lint, $modules_run test modules and the closure check ran."
  exit "$GATE_FULL_GREEN"
fi

# A reduced run that skipped nothing, or that ran nothing, is a broken rule
# rather than a good result, and either way it is not a green tick.
if [ "$modules_not_run" -lt 1 ]; then
  echo "gate: the contract is absent and no test module said it needed it." >&2
  echo "gate: tests/contract_absence.py is not doing what this run depends on." >&2
  exit 1
fi
if [ "$modules_run" -lt 1 ]; then
  echo "gate: the contract is absent and nothing was left to run." >&2
  exit 1
fi

echo "gate: contract absent: $((checks_not_run + 1)) checks not run"
while IFS=$'\t' read -r kind what why; do
  [ -n "$what" ] || continue
  echo "gate:   not run: $what — $why"
done <"$not_run"
echo "gate:   not run: closure (articles 13 and 14) — it installs the contract to measure it"
echo "gate: reduced green — format, lint and $modules_run of $modules_present test modules ran."
echo "gate: A check counted above is a test module, a single test, or a named step. The"
echo "gate: tests inside a module that would not import cannot be counted, and are not:"
echo "gate: this run does not know how many of them there are."
echo "gate: This is not a pass. It proves nothing about the contract, nothing about the"
echo "gate: installed closure of articles 13 and 14, and — read the list above rather than"
echo "gate: this line — nothing about this client against a daemon. Point"
echo "gate: SAYFIRST_CONTRACT_SOURCE at a checkout of the control plane repository, and"
echo "gate: this becomes the full gate."
exit "$GATE_REDUCED_GREEN"
