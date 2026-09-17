# SPDX-License-Identifier: Apache-2.0
"""Article 0: nothing is published before the operator's own act.

Article 0 forbids anything under the decided name — no package on an index, no
public repository, no announcement — until the marks are filed. The act that
publishes is therefore the operator's tag and nothing else, and this guard keeps
the workflow from acquiring a second one by accident: a `branches:` added under
`push` for convenience, a `pull_request:` added to « test the release path », a
publish step that stops needing the build that checked the tag.

Three more rules, each this repository's own:

* A release is never cut from a reduced gate. The gate has three outcomes rather
  than two, 75 being « the contract was absent and some checks did not run », and
  a release built on that would be a release nothing had checked against the
  contract. The workflow reads the status and refuses it; this guard reads that
  it does.
* A release reads the contract from the PUBLIC control plane, at the tag this
  client's own pin names, with no credential. A release happens after
  publication and in a fixed order — the contract before the client — so the
  repository `ci.yml` reaches with a read token is the wrong one here, and the
  token would be a capability a published workflow has no reason to hold. The
  public base is not spelled here either: it is read from
  `tests/test_pointers_survive_publication.py`, which is where this project
  keeps the names publication creates, so a rename lands in one place.
* The version is read, never spelled. The tag the contract is read at is `v`
  followed by the pin in `pyproject.toml`, and this guard runs the workflow's
  own reading of that file to see what it yields.

Read as text rather than as parsed YAML: this repository installs no YAML
reader, and `tests/test_gate_modes.py` reads the other workflow the same way.
Every assertion names the exact line it wants, so a reformatting that breaks it
fails loudly rather than passing vacuously — with one deliberate exception. The
two triggers this file exists to keep out are matched **by shape**, because each
has more than one spelling and an exact line bites on only one of them: a
`not in` assertion over raw lines catches `branches:` with a block under it and
walks past `branches: [main]`, which is the form GitHub's own documentation uses
and the form a convenience edit takes. Both shape readings are planted against a
mutated copy of the real file, since a `not in` assertion is proven by a mutation
and by nothing else.

Three rules are read out of the control plane's own workflow guard rather than
invented here, because two conventions for one rule is how two repositories stop
agreeing about it: the checkout depth — `fetch-depth: 0` within three lines of
every `actions/checkout@` — the shape of the two refused triggers, and the
reading of a permission block whole, so that « and nothing else » is assertable
about the scopes a job holds.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from test_pointers_survive_publication import NEVER_PUBLISHED, PUBLIC_CONTROL_PLANE

REPOSITORY = Path(__file__).resolve().parents[1]
WORKFLOW = REPOSITORY / ".github" / "workflows" / "release.yml"

#: The interpreter every `python` line of the workflow goes through. The
#: runner's system interpreter is never used: this project's own `uv run` cannot
#: resolve the contract packages from an index, so the reader is run with
#: `--no-project` and an interpreter named outright.
INTERPRETER = "uv run --no-project --python 3.12 python"

#: The artefact checker, pinned. The control plane's release workflow pins the
#: same version, so the two distributions of one release are checked by one set
#: of rules; an unpinned checker is a check that can change between two releases
#: without either release changing, and the change arrives as a red release
#: rather than as a diff somebody reviewed.
ARTEFACT_CHECKER = "uvx twine@7.0.0 check dist/*"

#: The uv this release is built with, and the version of it, as the two lines a
#: workflow spells them on. The control plane's release workflow pins the same
#: action for the same reason: a release built by whichever uv resolved that day
#: is a release nobody can cut twice.
UV_ACTION = "      - uses: astral-sh/setup-uv@v5"
UV_VERSION = '          version: "0.12.5"'

#: The action that hands the built distributions to the index, however it is
#: pinned. Every reference is read rather than one: a second use added beside
#: the first is the use nobody asserted about.
PUBLISH_ACTION = re.compile(r"pypa/gh-action-pypi-publish@\S+")

#: The only pinning this workflow accepts for it: a release of the action, named
#: in full, like the uv version and the artefact checker beside it. `@release/v1`
#: — the form the action's own documentation offers — is a ref that moves, so the
#: last step between a build and the world could change its behaviour between two
#: releases without either release changing. The control plane's release workflow
#: is held to the same form.
PINNED_RELEASE = re.compile(r"pypa/gh-action-pypi-publish@v\d+\.\d+\.\d+")

#: The public repository the contract is read from, as a workflow spells a
#: repository: owner and name, derived from the URL the publication guard holds.
PUBLIC_CONTROL_PLANE_REPOSITORY = PUBLIC_CONTROL_PLANE.removeprefix("https://github.com/")


def _lines() -> list[str]:
    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def _keys(lines: list[str], *names: str) -> list[str]:
    """Every line that opens one of these mapping keys, in any spelling of its value.

    By shape rather than by exact line, because `branches: [main]` and
    `branches:` with a block under it are the same defect, and only the second
    is a line anybody would think to write down. Comment lines are not keys, and
    the exclusion is not a nicety here: this workflow's own header names both of
    the keys it refuses to carry, and a reading without it would report the
    sentence that promises the rule as a breach of it.

    The control plane's twin guard reads the same shape, name for name.
    """
    return [
        line
        for line in lines
        if not line.strip().startswith("#")
        and line.strip().startswith(tuple(f"{name}:" for name in names))
    ]


def _branch_filters(lines: list[str]) -> list[str]:
    """Anything that attaches this workflow to a branch rather than to a tag."""
    return _keys(lines, "branches", "branches-ignore")


def _ordinary_traffic_triggers(lines: list[str]) -> list[str]:
    """Anything that starts this workflow on traffic no operator asked for."""
    return _keys(lines, "pull_request", "pull_request_target")


def _owned_by(lines: list[str], number: int) -> list[str]:
    """The lines the mapping key on this line owns: those indented deeper, to the
    next sibling.

    What makes "and nothing else" assertable about a permission block: the scope
    that is present can be read from a substring, and the scope that is absent
    only from the whole block. Read out of the control plane's own workflow
    guard, where it does the same job.
    """
    header = lines[number]
    indent = len(header) - len(header.lstrip())
    owned: list[str] = []
    for line in lines[number + 1 :]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        owned.append(line)
    return owned


def _permission_blocks(lines: list[str]) -> list[list[str]]:
    """Every `permissions:` mapping in these lines, whole, in the order they appear.

    Every block and not the two a reader thought to name: a scope granted to a
    job nobody asserted about is a scope nobody reads, and the job that builds is
    the one a convenience edit reaches for when a step wants to push. A third
    block therefore arrives as a third entry rather than as silence.
    """
    return [
        _owned_by(lines, number)
        for number, line in enumerate(lines)
        if line.strip() == "permissions:"
    ]


def _publish_refs(lines: list[str]) -> list[str]:
    """Every reference to the publishing action, as this workflow pins it.

    Comment lines are not references: the comment beside the step explains the
    pinning, and a guard that read its own explanation as a use would be
    reporting on prose.
    """
    return [
        found
        for line in lines
        if not line.strip().startswith("#")
        for found in PUBLISH_ACTION.findall(line)
    ]


def _plant(lines: list[str], after: str, added: list[str]) -> list[str]:
    """A copy of the real file's lines with something inserted after this line.

    A mutated copy and never the file itself: a guard that rewrote the tree to
    prove itself would be a guard that can leave the tree rewritten.
    """
    number = lines.index(after)
    return [*lines[: number + 1], *added, *lines[number + 1 :]]


def _publish_job(lines: list[str]) -> list[str]:
    """The publish job's own lines, so its keys are never read from another job's."""
    body = lines[lines.index("  publish:") + 1 :]
    end = next(
        (
            number
            for number, line in enumerate(body)
            if line.strip() and not line.startswith("    ")
        ),
        len(body),
    )
    return body[:end]


def _unpinned_release_tools(text: str) -> list[str]:
    """Every tool this workflow runs on the way to the index that names no version.

    One reading of the rule, so that the green case and the planted mutations
    below ask the same question: two copies of one rule is how a guard and its
    own probe stop agreeing. The gate workflow is deliberately not held to this
    — it reports on the tree under the toolchain of the day, which is what a
    gate is for.
    """
    lines = text.splitlines()
    problems: list[str] = []
    if UV_ACTION not in lines:
        problems.append("the uv this release is built with is not the pinned action")
    if UV_VERSION not in lines:
        problems.append("the uv action asks for no version, so it installs the one of the day")
    if not re.search(r"uvx twine@\d+\.\d+\.\d+ check", text):
        problems.append("the artefact checker names no version")
    refs = _publish_refs(lines)
    if not refs:
        problems.append("nothing here publishes, so the rule below would hold vacuously")
    problems.extend(
        f"the action that publishes is pinned to {ref}, which is not a release"
        for ref in refs
        if not PINNED_RELEASE.fullmatch(ref)
    )
    return problems


def _shallow(lines: list[str]) -> list[str]:
    """Every checkout that does not carry the history the gate reads.

    The same rule, and the same three-line window, as the control plane's
    `tests/test_public_gate_runs_the_suite.py`: the gate reads a sibling
    checkout with `git archive <ref>`, and a checkout fetched shallow has no ref
    to archive. Scoped to this workflow, which is the file this module reads;
    `ci.yml` is held by `tests/test_gate_modes.py`.

    `ci.yml` checks this repository out shallow and is right to. Nothing the
    gate runs reads this repository's own history — `git ls-files` is the whole
    of it — and only the CONTRACT-SOURCE checkout has to carry a ref, because
    that is the one `gate.sh` archives out of. The rule here is therefore a
    convention wider than its need, deliberately, because the need is invisible
    at the line where the mistake is made: a reader who arrives at `ci.yml`
    holding this rule is not looking at a broken file.
    """
    return [
        f"{number + 1}: {line.strip()}"
        for number, line in enumerate(lines)
        if "actions/checkout@" in line
        and "fetch-depth: 0" not in "\n".join(lines[number + 1 : number + 4])
    ]


def _case_branches(script: str) -> dict[str, str]:
    """The branches of a step's `case`, by label, read out of the shell it runs.

    A three-outcome status is a three-branch case, and what each branch DOES is
    the half worth reading: a `75)` whose `exit` has been deleted still carries
    every substring a reader would think to grep for.
    """
    found = re.findall(r"^\s*(\S+)\)\n(.*?)^\s*;;\s*$", script, re.MULTILINE | re.DOTALL)
    labels = [label for label, _ in found]
    assert len(set(labels)) == len(labels), f"two branches share a label: {labels}"
    return dict(found)


def _step_script(identifier: str) -> str:
    """The shell of the step carrying this `id:`, as the runner would type it."""
    lines = _lines()
    start = lines.index(f"        id: {identifier}")
    after = range(start, len(lines))
    marker = next(number for number in after if lines[number] == "        run: |")
    body: list[str] = []
    for line in lines[marker + 1 :]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line[10:])
    return "\n".join(body)


def _run_step_script(script: str, where: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run a step's shell the way the runner does, and hand back what it wrote.

    `bash -e -o pipefail` is the default shell of a GitHub job, and the
    difference matters: a reading that only fails safely under one of the two
    shells is a reading that fails unsafely on the runner.
    """
    output = where / "github-output"
    output.touch()
    finished = subprocess.run(
        ("bash", "-e", "-o", "pipefail", "-c", script),
        cwd=where,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(where / "github-summary"),
        },
    )
    return finished, output


def pinned_contract_version(root: Path) -> str:
    """The contract version this client depends on, read the way the gate reads it."""
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pinned = [
        requirement
        for requirement in project["dependencies"]
        if requirement.startswith("sayfirst-contract==")
    ]
    assert len(pinned) == 1, pinned
    return pinned[0].split("==", 1)[1]


def test_the_release_workflow_exists_and_is_read_by_this_guard() -> None:
    """ANTI-VACUITY. A missing file would make every assertion below pass."""
    assert WORKFLOW.is_file(), WORKFLOW
    assert len(_lines()) >= 40
    assert _lines()[0] == "# SPDX-License" + "-Identifier: Apache-2.0"


def test_it_does_nothing_on_a_push_to_a_branch_or_on_a_pull_request() -> None:
    """Article 0: a release path that runs on ordinary traffic is a release path
    that will one day publish on ordinary traffic.

    By shape, so that every spelling of each of the two triggers is refused and
    not only the one a reader would think to write down. The header of the file
    this reads promises exactly that, in prose, to whoever opens it.
    """
    lines = _lines()
    assert _ordinary_traffic_triggers(lines) == []
    assert _branch_filters(lines) == [], "a branch filter under push means this runs on a branch"
    assert '    tags: ["v*"]' in lines


def test_the_guard_still_catches_a_branch_filter_added_for_convenience() -> None:
    """WATCHED FIRING. `branches: [main]` is the spelling a convenience edit takes.

    The `tags:` assertion above does not backstop it — the tags line survives
    that edit — so this planted copy of the real file is the whole proof that the
    refusal bites. The ignore form is planted too: it attaches this workflow to
    every branch but one, which is the same defect written the other way round.
    """
    original = WORKFLOW.read_text(encoding="utf-8")
    planted = original.replace('    tags: ["v*"]', '    tags: ["v*"]\n    branches: [main]')
    assert planted != original, "the plant changed nothing"
    caught = _branch_filters(planted.splitlines())
    assert caught == ["    branches: [main]"], (
        f"FAIL a planted inline branch filter was not caught: {caught}"
    )
    assert _branch_filters('    branches-ignore: ["wip"]'.splitlines()), "the ignore form too"


def test_the_guard_still_catches_a_pull_request_trigger_added_to_try_the_path() -> None:
    """WATCHED FIRING. The other way a release path acquires a second act that
    starts it, in the three spellings it takes: the block form, the empty
    mapping, and the trigger that runs against the base repository."""
    original = WORKFLOW.read_text(encoding="utf-8")
    planted = original.replace("  workflow_dispatch:", "  pull_request:\n  workflow_dispatch:")
    assert planted != original, "the plant changed nothing"
    caught = _ordinary_traffic_triggers(planted.splitlines())
    assert caught == ["  pull_request:"], (
        f"FAIL a planted pull-request trigger was not caught: {caught}"
    )
    assert _ordinary_traffic_triggers(["  pull_request: {}"]), "the empty-mapping form too"
    assert _ordinary_traffic_triggers(["  pull_request_target:"]), "and the base-repository one"


def test_the_dry_run_is_started_by_hand_and_publishes_nothing() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "  workflow_dispatch:" in text
    assert "      publish:" in text
    assert "        default: false" in text


def test_a_dispatch_asking_to_publish_is_refused_rather_than_ignored() -> None:
    """An input nothing reads is a control that lies.

    What makes a dispatch publish nothing is the `publish` job's own condition,
    which no input can reach. A switch beside it would therefore be obeyed by
    nobody and reported to nobody, so one step reads it and fails the run with
    the reason. Held here because deleting that step returns the switch to being
    silently ignored, which is the defect it was added for.
    """
    lines = _lines()
    assert "        if: github.event_name == 'workflow_dispatch' && inputs.publish" in lines
    refusal = [line for line in lines if "publish by tagging" in line]
    assert len(refusal) == 1, refusal
    assert "::error::" in refusal[0]


def test_the_publish_job_runs_only_for_a_tag_and_only_after_the_build() -> None:
    lines = _lines()
    assert "    needs: build" in lines
    assert "    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in lines


def test_the_publish_job_uses_trusted_publishing_into_a_named_environment() -> None:
    """Whether the environment demands a reviewer is a setting of the repository,
    which no file here can read; the checklist carries it and this test does not
    claim it."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "      name: pypi" in text
    assert "      id-token: write" in text
    refs = _publish_refs(_lines())
    assert refs, "nothing here publishes"
    assert all(PINNED_RELEASE.fullmatch(ref) for ref in refs), refs
    assert "password:" not in text, "a stored token is not trusted publishing"


def test_the_tools_that_cut_a_release_are_pinned_to_one_version() -> None:
    """A release whose own toolchain is whichever version resolved that day is a
    release nobody can cut twice.

    Three tools stand between this tree and the index: the uv the distribution
    is built with, which decides what the distribution is; the artefact checker,
    which is the last thing that reads it; and the action that uploads it. Each
    is named with a version here. The control plane's release workflow pins the
    first two to the same versions, so one release's distributions are built and
    checked alike.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert _unpinned_release_tools(text) == []
    assert "uvx twine check dist/*" not in text, "an unpinned checker is whatever is served today"


def test_the_pinning_rule_catches_a_toolchain_that_moves() -> None:
    """WATCHED FIRING, one planted mutation per pin, against copies of the real
    file. A rule whose only evidence is that it passes today would also pass if
    it had stopped applying."""
    original = WORKFLOW.read_text(encoding="utf-8")
    for mutation, was, becomes in (
        ("the uv action", UV_ACTION, "      - uses: astral-sh/setup-uv@main"),
        ("the uv version", UV_VERSION, "          version: latest"),
        ("the artefact checker", ARTEFACT_CHECKER, "uvx twine check dist/*"),
        (
            "the publish action",
            "uses: pypa/gh-action-pypi-publish@v1.14.2",
            "uses: pypa/gh-action-pypi-publish@release/v1",
        ),
    ):
        planted = original.replace(was, becomes)
        assert planted != original, f"the plant for {mutation} changed nothing"
        assert _unpinned_release_tools(planted), f"FAIL {mutation} was not caught: {becomes}"


def test_no_job_holds_a_permission_it_does_not_need() -> None:
    """A publishing job that could also push is a different job.

    Each block is asserted whole and not as a substring: what matters about the
    publish job is the scope it does *not* hold, and a `contents: write` added
    beside `id-token: write` satisfies every assertion that only asks what is
    present. Every block in the file is read, so a scope granted to the job that
    BUILDS — the one a step that wanted to push would be added to — arrives as a
    third entry here rather than as silence.
    """
    lines = _lines()
    assert _permission_blocks(lines) == [["  contents: read"], ["      id-token: write"]]
    assert _permission_blocks(_publish_job(lines)) == [["      id-token: write"]]


def test_the_permission_rule_catches_a_scope_a_job_does_not_need() -> None:
    """WATCHED FIRING, one planted mutation per rule: a build job that granted
    itself the right to push, and a publish job that kept the right to publish
    and took the right to write beside it."""
    lines = _lines()
    for mutation, planted in (
        (
            "a build job granted contents: write",
            _plant(lines, "  build:", ["    permissions:", "      contents: write"]),
        ),
        (
            "a publish job granted contents: write",
            _plant(lines, "      id-token: write", ["      contents: write"]),
        ),
    ):
        assert planted != lines, f"the plant for {mutation} changed nothing"
        assert _permission_blocks(planted) != [["  contents: read"], ["      id-token: write"]], (
            f"FAIL {mutation} was not caught"
        )


def test_a_reduced_gate_never_becomes_a_release() -> None:
    """The gate's third outcome is not a pass, and a release is the last place
    it could be mistaken for one.

    Read as the three branches of the gate step's own `case` rather than as
    three substrings of the file: what has to hold is that `75)` LEAVES the run
    non-zero and that no status falls through unread. A branch that still says
    `::error::` and no longer exits cuts a release nothing checked against the
    contract, and this repository already holds `ci.yml` to the three-branch
    shape rather than to a mention of each number
    (`tests/test_gate_modes.py::test_both_gate_jobs_decide_every_status`).
    """
    script = _step_script("gate")
    assert "./scripts/gate.sh" in script
    branches = _case_branches(script)
    assert set(branches) == {"0", "75", "*"}, sorted(branches)
    assert "exit" not in branches["0"], "full green is the only pass, and it exits nothing"
    assert re.search(r"^\s*exit [1-9]\d*$", branches["75"], re.MULTILINE), branches["75"]
    assert "::error::" in branches["75"]
    assert "a release is never cut from a reduced gate" in branches["75"]
    assert 'exit "$status"' in branches["*"], "a status nobody reads is a status nobody refuses"


def test_the_build_checks_the_tag_against_the_version_and_the_artefacts() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert f'{INTERPRETER} scripts/release_version.py --expect "${{GITHUB_REF_NAME#v}}"' in text
    assert "uv build --out-dir dist" in text
    assert ARTEFACT_CHECKER in text


def test_the_artefact_checker_is_pinned() -> None:
    """Auto-walked: every line that runs the checker, not the one pinned by hand.

    The version is part of the check. An unpinned `uvx twine check` resolves
    whatever the index offers on the day, so two releases a week apart can be
    checked by two different sets of rules, and the day the rules change the
    project learns it from a red release rather than from a diff. The control
    plane's release workflow pins the same version, so one release's
    distributions are checked alike.
    """
    running = [
        line.strip() for line in _lines() if not line.lstrip().startswith("#") and "twine" in line
    ]
    assert len(running) == 1, running
    assert ARTEFACT_CHECKER in running[0], running[0]
    assert re.search(r"uvx twine@\d+\.\d+\.\d+ check", running[0]), running[0]


def test_no_line_of_the_workflow_runs_the_runners_own_interpreter() -> None:
    """Auto-walked: every `python` in the file, not the ones someone remembered.

    `uv run` without `--no-project` would try to resolve this project, whose
    contract packages are on no index, and a bare `python` would be whatever the
    runner image happens to ship. Two lines need an interpreter; both name one.
    """
    running = [
        line.strip()
        for line in _lines()
        if not line.lstrip().startswith("#") and re.search(r"(?<!-)\bpython\b", line)
    ]
    assert len(running) == 2, running
    for line in running:
        assert f"{INTERPRETER} scripts/release_version.py" in line, line


def test_the_contract_is_read_from_the_public_repository_and_with_no_credential() -> None:
    """A published workflow holds no capability a stranger reading it does not.

    `ci.yml` reaches a repository that is not public yet and carries a read
    token to do it. This workflow runs after publication, so it reaches the
    published base instead — and a token here would be a secret in the one file
    that also holds the right to publish.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert f"repository: {PUBLIC_CONTROL_PLANE_REPOSITORY}" in text
    assert NEVER_PUBLISHED not in text, (
        f"the release workflow names {NEVER_PUBLISHED}, which is never published: after "
        f"publication there is nothing at that name for a runner to check out"
    )
    assert "secrets." not in text, "a release workflow that reads a secret is one a fork cannot"
    withheld = [line.strip() for line in _lines() if re.fullmatch(r"\s*token:.*", line)]
    assert withheld == [], withheld


def test_the_contract_is_read_at_the_tag_this_client_pins_and_the_version_is_read_not_spelled(
    tmp_path: Path,
) -> None:
    """One reading of the pin, run here to see what it yields.

    The workflow checks the control plane out at `v` + the pinned contract
    version and points the gate at the same ref. Neither is spelled: a step
    reads the project file, and this test runs that step's own shell over the
    real project file rather than a second reading of the rule written here.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "ref: ${{ steps.contract.outputs.tag }}" in text
    assert "SAYFIRST_CONTRACT_REF: ${{ steps.contract.outputs.tag }}" in text
    version = pinned_contract_version(REPOSITORY)
    assert version not in text, (
        f"the workflow spells the pinned contract version {version}; it is read from "
        f"pyproject.toml so that the two cannot drift apart"
    )

    script = _step_script("contract")
    assert "pyproject.toml" in script
    shutil.copy(REPOSITORY / "pyproject.toml", tmp_path / "pyproject.toml")
    finished, output = _run_step_script(script, tmp_path)
    assert finished.returncode == 0, finished.stderr
    assert f"tag=v{version}" in output.read_text(encoding="utf-8")


def test_a_project_file_that_pins_no_contract_stops_the_release(tmp_path: Path) -> None:
    """WATCHED FIRING, on the reading above. A step that silently produced `v`
    would check the control plane out at a ref nobody named, and the gate would
    report on whatever that resolved to."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sayfirst-cli"\nversion = "0.0.0"\ndependencies = []\n',
        encoding="utf-8",
    )
    finished, output = _run_step_script(_step_script("contract"), tmp_path)
    assert finished.returncode != 0
    assert "::error::" in finished.stdout
    assert output.read_text(encoding="utf-8") == ""


def test_a_project_file_whose_two_pins_disagree_stops_the_release(tmp_path: Path) -> None:
    """WATCHED FIRING on the assumption the derivation rests on.

    One tag of the control plane is checked out, and this client pins two of the
    distributions that tag builds. The tag is derived from the contract pin
    because the control plane moves every distribution to one version together —
    its rule, not this repository's — so two pins naming two versions name no
    tag at all. The step says so before anything is checked out, instead of
    reading the contract at one version and letting the other pin fail an
    install later.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sayfirst-cli"\nversion = "9.9.9"\n'
        'dependencies = ["sayfirst-contract==9.9.9", "sayfirst-boundary==9.9.8"]\n',
        encoding="utf-8",
    )
    finished, output = _run_step_script(_step_script("contract"), tmp_path)
    assert finished.returncode != 0
    assert "::error::" in finished.stdout
    assert "the pins disagree" in finished.stdout
    assert output.read_text(encoding="utf-8") == ""


def test_every_checkout_carries_the_history_the_gate_reads() -> None:
    lines = _lines()
    assert _shallow(lines) == []
    # Anti-vacuity: a workflow that checked nothing out would pass the line above.
    assert [line for line in lines if "actions/checkout@" in line]


def test_the_depth_rule_catches_a_planted_shallow_checkout() -> None:
    """WATCHED FIRING. A rule whose only evidence is that it passes today would
    also pass if it had stopped applying."""
    planted = [
        "      - uses: actions/checkout@v5",
        "        with:",
        "          path: sayfirst-cli",
    ]
    assert _shallow(planted)
    assert _shallow([*planted[:2], "          fetch-depth: 0", planted[2]]) == []
