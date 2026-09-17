# SPDX-License-Identifier: Apache-2.0
"""The gate has three outcomes, and the workflow renders three; here they are held.

    "an absence — a missing record, an unreachable control plane, an empty list
    — is never rendered as a negative fact, a zero or a healthy state"
                                                — constitution, article 2

`scripts/gate.sh` can now finish without the contract. That is worth having and
it is exactly the kind of change that decays into a lie: the reduced run keeps
working, the reason it is reduced stops being visible, and a green tick comes to
mean two different things. So the three outcomes are read out of the script
itself, the workflow is required to render each of them differently, and the
status the script reserves for a reduced run is required to be one the workflow
knows about — a script and a workflow that stopped agreeing about that number
would fail open, and green.

The workflow is read as text on purpose. Its own claims — every check is the
gate, nothing here runs a test another way, the control plane is read at its
public name and with no credential — are claims about what the file says, and
the file is what CI executes.

**What publication changed here, and what it did not.** The contract's
repository is open, so the checkout this workflow makes of it carries no
credential and names no secret; the rules below therefore ask for the absence of
a credential rather than for its careful handling, which is the stronger
question and the one a stranger reading the file can check. What did not change
is the reduced leg: a machine that cannot reach that repository still gets a
contract that is simply absent, and the three outcomes above are still three.
The two legs now run side by side instead of one instead of the other, so
neither is conditional, and that too is held below — a condition is how one of
them would quietly stop running.

The public repository's name is not spelled here. It is read from
`tests/test_pointers_survive_publication.py`, which is where this project keeps
the names publication creates, so a rename lands in one place; the release
workflow's guard reads it from there for the same reason.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from test_pointers_survive_publication import NEVER_PUBLISHED, PUBLIC_CONTROL_PLANE

REPOSITORY = Path(__file__).resolve().parents[1]
GATE = REPOSITORY / "scripts" / "gate.sh"
WORKFLOW = REPOSITORY / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = REPOSITORY / ".github" / "workflows" / "release.yml"

GATE_TEXT = GATE.read_text(encoding="utf-8")
WORKFLOW_TEXT = WORKFLOW.read_text(encoding="utf-8")

#: The control plane as a runner names it in a `repository:` key, derived from
#: the URL rather than written out a second time.
PUBLIC_CONTROL_PLANE_REPOSITORY = PUBLIC_CONTROL_PLANE.removeprefix("https://github.com/")


def _code(text: str) -> str:
    """The workflow without its comments: what the runner acts on.

    The comments here quote the defect this file exists to keep out, so a guard
    that grepped the whole file would fire on the sentence explaining it.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


WORKFLOW_CODE = _code(WORKFLOW_TEXT)

#: The action versions this repository will run. `v4` runs on Node 20, which
#: GitHub deprecated; a warning nobody clears is a warning nobody reads.
CHECKOUT = "v5"

#: The job that reads the sign-offs of a change. Article 15 asks for the trailer
#: and article 16 calls the check required; the job is where "runs on every pull
#: request" stops being a sentence and becomes a file.
SIGN_OFF_JOB = "developer-certificate-of-origin"


def _declared(name: str) -> int:
    """A `readonly NAME=<number>` line of the gate, read from the gate."""
    found = re.search(rf"^readonly {name}=(\d+)$", GATE_TEXT, re.MULTILINE)
    assert found, f"{GATE} declares no {name}"
    return int(found.group(1))


def _lines_under(header: str) -> list[str]:
    """The indented lines below a top-level `header:` of the workflow."""
    lines = WORKFLOW_TEXT.splitlines()
    for index, line in enumerate(lines):
        if line == f"{header}:":
            body = []
            for follower in lines[index + 1 :]:
                if follower and not follower.startswith(" "):
                    break
                body.append(follower)
            return body
    raise AssertionError(f"{WORKFLOW} has no top-level {header!r}")


def _jobs() -> dict[str, list[str]]:
    """Every job of the workflow, by identifier, with the lines it owns."""
    jobs: dict[str, list[str]] = {}
    current: str | None = None
    for line in _lines_under("jobs"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if current is not None:
                jobs[current].append(line)
            continue
        if re.fullmatch(r"  [a-z0-9-]+:", line):
            current = stripped[:-1]
            jobs[current] = []
        elif current is not None:
            jobs[current].append(line)
    assert len(jobs) >= 3, f"{WORKFLOW} was not parsed into jobs: {sorted(jobs)}"
    return jobs


def _name(lines: list[str]) -> str:
    for line in lines:
        found = re.fullmatch(r"    name: (.+)", line)
        if found:
            return found.group(1)
    raise AssertionError("a job of the workflow has no name")


def _gate_jobs() -> dict[str, list[str]]:
    return {
        identifier: lines
        for identifier, lines in _jobs().items()
        if any("scripts/gate.sh" in line for line in lines)
    }


def test_the_gate_declares_three_outcomes_and_not_two() -> None:
    """Article 2's three-value rule, applied to the gate's own status surface."""
    full, reduced = _declared("GATE_FULL_GREEN"), _declared("GATE_REDUCED_GREEN")

    assert full == 0
    assert reduced != full, "a reduced run and a full run cannot share a status"
    assert reduced != 1, "a reduced run cannot share a status with an ordinary failure"


def test_the_reduced_status_is_reached_by_exactly_one_path() -> None:
    """One `exit` writes it, at the end of the reduced run, after the count."""
    assert GATE_TEXT.count('exit "$GATE_REDUCED_GREEN"') == 1
    assert re.search(r"^gate: contract absent: ", GATE_TEXT, re.MULTILINE) is None
    assert 'echo "gate: contract absent: $((checks_not_run + 1)) checks not run"' in GATE_TEXT


def test_a_failure_can_never_be_read_as_a_reduced_run() -> None:
    """A tool that happened to exit 75 would otherwise forge a green tick."""
    assert 'if [ "$status" -eq "$GATE_REDUCED_GREEN" ]; then' in GATE_TEXT
    assert "trap on_failure ERR" in GATE_TEXT


def test_the_workflow_knows_the_status_the_gate_reserves() -> None:
    """The number lives in the script; the workflow is required to have read it."""
    reduced = _declared("GATE_REDUCED_GREEN")
    for identifier, lines in _gate_jobs().items():
        assert any(re.fullmatch(rf"\s*{reduced}\)", line) for line in lines), (
            f"the {identifier} job does not say what it does with status {reduced}"
        )


def test_both_gate_jobs_decide_every_status() -> None:
    """Full, reduced, failure: each job answers all three, the last by falling through."""
    jobs = _gate_jobs()
    assert len(jobs) == 2, f"expected a full job and a reduced job, found {sorted(jobs)}"
    for identifier, lines in jobs.items():
        body = "\n".join(lines)
        for branch in (r"^\s*0\)", r"^\s*75\)", r"^\s*\*\)"):
            assert re.search(branch, body, re.MULTILINE), f"{identifier} ignores {branch}"


def test_a_reduced_run_is_not_rendered_as_an_ordinary_green_tick() -> None:
    """The job's own name carries the absence, before anyone opens the summary."""
    reduced = [
        identifier
        for identifier, lines in _gate_jobs().items()
        if "reduced" in _name(lines).lower()
    ]
    assert len(reduced) == 1, f"expected one reduced job, found {reduced}"
    name = _name(_gate_jobs()[reduced[0]])
    assert "absent" in name.lower(), name
    assert "not run" in name.lower(), name
    assert len({_name(lines) for lines in _jobs().values()}) == len(_jobs())


def test_the_reduced_job_says_how_many_checks_did_not_run_and_what_would_fix_it() -> None:
    """A count nobody can find is a count nobody reads, and a remedy nobody
    names is a reduced tick a reader can do nothing about.

    The remedy is read for by the name of the thing that supplies the contract —
    `SAYFIRST_CONTRACT_SOURCE` — rather than by the name of a secret. There is
    no secret any more; a rule that still asked for one would go red on the
    tree being right.
    """
    body = "\n".join(_gate_jobs()[_reduced_identifier()])
    assert "gate: contract absent:" in body, "the reduced job never reads the count"
    assert "GITHUB_STEP_SUMMARY" in body
    assert "::warning::" in body
    assert "SAYFIRST_CONTRACT_SOURCE" in body, "the reduced job never says what would make it full"


def test_the_reduced_job_makes_no_checkout_of_the_control_plane() -> None:
    """This leg IS the machine that has nothing, so it must keep having nothing.

    A `repository:` added here — for convenience, now that the checkout needs no
    credential — would make the reduced leg full and leave the workflow with two
    full legs and a name that lied about one of them. `token:` is refused beside
    it because the whole file holds none and the rule is cheaper to keep here
    than to rediscover.
    """
    body = _code("\n".join(_gate_jobs()[_reduced_identifier()]))
    assert "repository:" not in body
    assert "token:" not in body


def test_no_checkout_falls_back_to_a_token_scoped_to_this_repository() -> None:
    """`secrets.X || github.token` is what turned an absent secret into `Not Found`."""
    assert "github.token" not in WORKFLOW_CODE


def test_the_contract_is_read_from_the_public_repository_and_with_no_credential() -> None:
    """Article 16: a fork reading this file holds everything this file needs.

    The strongest form of "the credential is handled carefully" is that there is
    no credential. So this asks for the absence of one, over the whole file and
    not only over the lines a runner acts on: a secret named in a comment is a
    secret somebody is about to use. The repository that is never published is
    refused by name for a different reason — after publication there is nothing
    at that name for a runner to check out.
    """
    assert f"repository: {PUBLIC_CONTROL_PLANE_REPOSITORY}" in WORKFLOW_TEXT
    assert NEVER_PUBLISHED not in WORKFLOW_TEXT, (
        f"the gate workflow names {NEVER_PUBLISHED}, which is never published: after "
        f"publication there is nothing at that name for a runner to check out"
    )
    assert "secrets." not in WORKFLOW_TEXT, "a gate a fork cannot run is not article 16's gate"
    withheld = [
        line.strip() for line in WORKFLOW_TEXT.splitlines() if re.fullmatch(r"\s*token:.*", line)
    ]
    assert withheld == [], withheld


def test_the_contract_tag_is_derived_once_and_read_the_same_by_both_workflows() -> None:
    """The tag is derived, never spelled, and derived once for both workflows.

    Two files now read the same pin to name the same tag, and two readings of
    one rule is how two files stop agreeing about it. So the derivation is held
    as ONE TEXT: the step carrying `id: contract` in each workflow, compared
    character for character. The version itself appears in neither — it is read
    from `pyproject.toml`, and a version spelled twice is a version that will
    eventually be spelled two ways.
    """
    script = _step_script(WORKFLOW_TEXT, "contract")
    # Anti-vacuity: a reader that found an empty step would make every
    # comparison below pass by having nothing to compare.
    assert len(script.splitlines()) >= 10, script
    assert "pyproject.toml" in script
    assert 'echo "tag=v${pinned}" >> "$GITHUB_OUTPUT"' in script
    release = _step_script(RELEASE_WORKFLOW.read_text(encoding="utf-8"), "contract")
    assert script == release, "the two workflows derive the contract's tag differently"

    assert "ref: ${{ steps.contract.outputs.tag }}" in WORKFLOW_TEXT
    assert "SAYFIRST_CONTRACT_REF: ${{ steps.contract.outputs.tag }}" in WORKFLOW_TEXT
    assert _pinned_contract_version() not in WORKFLOW_TEXT, (
        "the workflow spells the pinned contract version; it is read from pyproject.toml "
        "so that the two cannot drift apart"
    )


def test_neither_leg_is_conditional_so_both_run_on_every_run() -> None:
    """A full leg and a reduced leg, side by side, on every push and every
    pull request.

    While the contract's repository needed a credential, which leg ran was
    decided by whether this repository held one, and a fork got the reduced leg
    alone. That question is gone, and what replaced it is both legs always: the
    full one proves the tree against the contract, the reduced one proves the
    reduced path still renders honestly. A condition on either — or a `needs:`
    reintroducing a job that decides between them — is how one of them quietly
    stops running, which is why the shape rather than the intention is held.
    """
    for identifier, lines in _gate_jobs().items():
        conditions = [line.strip() for line in lines if line.strip().startswith("if:")]
        assert conditions == [], f"{identifier} runs only sometimes: {conditions}"
        waits = [line.strip() for line in lines if line.strip().startswith("needs:")]
        assert waits == [], f"{identifier} waits on another job: {waits}"


def test_every_checkout_runs_on_a_supported_node() -> None:
    """Auto-walked: every pin in the file, not the ones someone remembered."""
    pinned = re.findall(r"actions/checkout@(\S+)", WORKFLOW_CODE)
    assert pinned, "the workflow checks nothing out"
    assert set(pinned) == {CHECKOUT}, pinned


def test_the_workflow_grants_read_and_nothing_else() -> None:
    """Article 16's "no private infrastructure" has a floor: this token can read."""
    granted = [line.strip() for line in _lines_under("permissions") if line.strip()]
    assert granted == ["contents: read"], granted
    assert WORKFLOW_CODE.count("permissions:") == 1, "a job grants itself something else"


def test_every_check_the_workflow_runs_is_the_gate() -> None:
    """A check that exists only in CI is a check nobody can reproduce locally.

    One exception, stated in this file's header and held by the test below it:
    the sign-off check, which has no range to be given off a pull request. The
    three names read for here are the tools `scripts/gate.sh` already runs, so a
    step that ran any of them a second way — with different options, against a
    different tree — would be a check nobody could reproduce even though the
    gate appears to cover it.
    """
    for tool in ("pytest", "ruff", "check_dependency_closure"):
        assert tool not in WORKFLOW_CODE, f"the workflow runs {tool} itself"


def test_the_workflow_runs_the_sign_off_check_on_every_pull_request() -> None:
    """Article 15: "runs on every pull request" is a claim about this file.

    Three things at once, because each alone would pass on a job that proved
    nothing: the job exists, it is gated to a pull request — it has no range to
    read on a push — and it checks the whole history out, since a shallow
    checkout has no range either and the script answers 2 rather than 0 for it.
    """
    jobs = _jobs()
    assert SIGN_OFF_JOB in jobs, f"{WORKFLOW} defines no sign-off job: {sorted(jobs)}"
    body = "\n".join(jobs[SIGN_OFF_JOB])
    assert "scripts/check_developer_certificate_of_origin.py" in body, body
    # The condition is held as a whole line, not a substring: a widening such as
    # `|| github.event_name == 'push'` would keep the substring and run the script on a
    # push with an empty range, which resolves and exits 0 rather than 2.
    assert "    if: github.event_name == 'pull_request'\n" in body, body
    assert "fetch-depth: 0" in body, "a shallow checkout has no range to read"


def test_the_sign_off_job_is_the_one_check_outside_the_gate() -> None:
    """A check that exists only in CI is a check nobody can reproduce, which is
    the rule the gate jobs are held to. This one is the stated exception and not
    a silence: it reads the commits of a change against the ref it started from,
    and a local run has no such range. Any OTHER job that ran a script of this
    repository would be the defect that rule exists to catch."""
    outside = {
        identifier
        for identifier, lines in _jobs().items()
        if "scripts/" in "\n".join(lines) and "scripts/gate.sh" not in "\n".join(lines)
    }
    assert outside == {SIGN_OFF_JOB}, outside


def _reduced_identifier() -> str:
    for identifier, lines in _gate_jobs().items():
        if "reduced" in _name(lines).lower():
            return identifier
    raise AssertionError("the workflow has no reduced job")


def _step_script(text: str, identifier: str) -> str:
    """The shell of the step carrying this `id:`, as the runner would type it.

    Over a text rather than over a file, because the one use of it compares the
    same step in two workflows and a reader that could only open one of them
    could not make that comparison.
    """
    lines = text.splitlines()
    start = lines.index(f"        id: {identifier}")
    marker = next(
        number for number in range(start, len(lines)) if lines[number] == "        run: |"
    )
    body: list[str] = []
    for line in lines[marker + 1 :]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line[10:])
    return "\n".join(body)


def _pinned_contract_version() -> str:
    """The contract version this client depends on, read the way the gate reads it."""
    project = tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pinned = [
        requirement
        for requirement in project["dependencies"]
        if requirement.startswith("sayfirst-contract==")
    ]
    assert len(pinned) == 1, pinned
    return pinned[0].split("==", 1)[1]
