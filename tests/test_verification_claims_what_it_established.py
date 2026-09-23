# SPDX-License-Identifier: Apache-2.0
"""One rule, seven ways it was broken: what a verification may assert.

**The rule.** `sayfirst instrument verify` may report `governed` for a point
only from evidence it actually READ, actually found SOUND, and actually tied to
the effect it watched — and only over a run it watched WHOLE. Anything it could
not establish is carried as an incompleteness, which is never a pass and never a
finding: `ungoverned` is a finding this client made and needs the chain read to
its end, `governed` is a pass and needs a record of THIS effect on evidence the
chain's own verification reports intact.

Every test here was written before the source that satisfies it, and every one
of them observed the defect it names first. They are grouped by the way the
rule was broken rather than by the function that broke it, because the seven
were one question and not seven call sites.

The end-to-end cases go through the shipped console script against a canned
daemon, for the reason `test_instrument_verify.py` gives: the verifier's whole
mechanism is a subprocess under an audit hook that can never be removed. The
component cases drive one consultation against a connection double, because
what they assert is an ORDER of reads and answers that no canned daemon can be
made to produce on demand.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from canned_daemon import answering_by_path
from documents import (
    ANOTHER_ACCOUNT,
    another_executions_effect_page,
    no_evidence_page,
    recorded_effect_page,
)
from governed_programs import CONSOLE_SCRIPT, instrument, plant_spawn_pack
from sayfirst_contract.client import Answered
from sayfirst_contract.generation import CONTRACT_GENERATION

from sayfirst_cli import exit_codes, reads
from sayfirst_cli.instrument import harness, manifest

#: The capability the planted spawn pack declares.
SPAWN = "process.spawn"

#: The point that pack watches, as the report spells it.
POINT = f"process-effects subprocess.Popen {SPAWN}"


def a_tree(root: Path, body: str, *, name: str = "tree") -> Path:
    """A one-file program, in a directory of its own."""
    tree = root / name
    tree.mkdir()
    (tree / "app.py").write_text(body, encoding="utf-8")
    return tree


def a_marking_tree(root: Path, marker: Path, *, name: str = "tree") -> Path:
    """A program whose spawned process leaves a file behind, or does not.

    The file is how « the effect was aborted » is told from « the verdict was
    written after the effect happened »: every assertion about a verdict is
    equally true of a hook that raised too late.
    """
    return a_tree(
        root,
        f"import subprocess\n\nsubprocess.run(['touch', {str(marker)!r}], check=True)\n",
        name=name,
    )


def verify(*argv: str, cwd: Path, timeout: float = 120) -> tuple[int, str, str]:
    """Run the real command the way a person runs it."""
    finished = instrument("verify", *argv, cwd=cwd)
    return finished.returncode, finished.stdout, finished.stderr


def verified(pack: Path, address: Path, tree: Path, *extra: str) -> tuple[int, str, str]:
    """`verify --ungoverned` over one pack and one program: the shape every case shares."""
    return verify(
        "--pack",
        str(pack),
        "--socket",
        str(address),
        "--scope",
        "local",
        "--ungoverned",
        *extra,
        "--",
        "app.py",
        cwd=tree,
    )


# --- 1. a record supports an effect only if it is THIS execution's ------------


def test_a_record_of_another_execution_does_not_make_this_effect_governed(
    tmp_path: Path,
) -> None:
    """P1-1. The chain holds one allow for the capability, recorded for somebody else.

    Nothing about that record says it preceded THIS effect: another principal
    asked it, on another connection, about another call. A verifier that counts
    it has proven that a decision exists somewhere in the scope, which is not
    the claim `docs/PACKS.md` makes and not a claim anybody wants.

    The chain WAS read to its end, so what this run established is an absence
    of any record of its own: that is a finding — exit 6 — and the effect is
    aborted, which the missing marker is the proof of.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-effect-happened"
    routes = {"/scopes/": (200, [no_evidence_page(), another_executions_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verified(pack, address, a_marking_tree(tmp_path, marker))
    assert code != 0, (stdout, stderr)
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert f"ungoverned {POINT} events=0" in stdout
    assert f"\n{harness.GOVERNED} {POINT}" not in f"\n{stdout}"
    assert not marker.exists(), "the effect happened although no decision of this run covered it"


def test_the_same_page_recorded_for_this_execution_is_governed(tmp_path: Path) -> None:
    """The anti-vacuity of the test above: the fixture pair differs in identity alone.

    Without this, « nothing is ever governed again » would satisfy the rule
    just as well, and a verifier that cannot pass is worth no more than one
    that cannot fail.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-effect-happened"
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verified(pack, address, a_marking_tree(tmp_path, marker))
    assert code == 0, (stdout, stderr)
    assert f"governed {POINT} events=1" in stdout
    assert marker.exists()


def test_the_two_fixtures_differ_in_nothing_but_the_identity_of_the_execution() -> None:
    """The invariant that replaces « vary what the matcher reads ».

    `tests/documents.py` varied the capability and the outcome, which were
    exactly the two members the matcher consumed, so no success fixture in this
    repository could see the association defect. What holds the pair apart now
    is the identity of the execution the record was made for — and this test
    fails if the two fixtures ever agree on it again.
    """
    ours = recorded_effect_page(SPAWN)["entries"][0]
    theirs = another_executions_effect_page(SPAWN)["entries"][0]
    assert ours["body"] == theirs["body"], "the pair must not differ in what the matcher reads"
    assert ours["principal"] != theirs["principal"]
    assert theirs["principal"] == ANOTHER_ACCOUNT
    assert ours["connection_id"] != theirs["connection_id"]


# --- 2. a record on evidence the chain itself calls damaged supports nothing --


def test_a_record_on_a_page_reporting_a_broken_chain_is_not_a_pass(tmp_path: Path) -> None:
    """P1-4. The page carries an allow and says, of its own range, `broken_at`.

    The served verification is the daemon's own reading of the chain it just
    handed over. Throwing it away and counting the record anyway is a claim
    made from evidence its own writer declared unusable, which is precisely the
    claim article 2 bounds by the evidence actually held.

    It is not `ungoverned` either: a damaged chain is not an established
    absence. The run carries the incompleteness, exits 7 — the code for a check
    that could not conclude — and the effect is still aborted, because an
    effect whose governance could not be established is not one this harness
    may let through.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-effect-happened"
    damaged = recorded_effect_page(SPAWN, condition="broken_at")
    routes = {"/scopes/": (200, [no_evidence_page(), damaged])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verified(pack, address, a_marking_tree(tmp_path, marker))
    assert code != 0, (stdout, stderr)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert f"\n{harness.GOVERNED} {POINT} events=1" not in f"\n{stdout}"
    assert f"{harness.UNJUDGED}: 1" in stdout
    assert not marker.exists(), "the effect happened on evidence the chain called broken"


# --- 3. a claim about the run covers the whole run, children included ---------

#: A program that meets one governed effect itself and forks a worker that
#: meets another. The worker catches its own abort and ends normally, which is
#: what an ordinary worker does with an exception it was written to survive.
FORKING_APP = """\
import multiprocessing
import subprocess


def worker():
    try:
        subprocess.run(["true"], check=True)
    except RuntimeError as refused:
        print("worker saw:", refused, flush=True)


subprocess.run(["true"], check=True)
child = multiprocessing.get_context("fork").Process(target=worker)
child.start()
child.join()
print("worker exit:", child.exitcode, flush=True)
"""


def test_a_run_that_forked_does_not_report_a_verdict_over_the_child(tmp_path: Path) -> None:
    """P1-2. Fork copies the hook, the cursor and the findings; only the parent's are written.

    The worker meets an effect no record covers, is aborted, catches the
    exception and exits 0. The parent joins it and — reading its own copies of
    objects the child changed in a memory the parent cannot see — reported
    `governed`, exit 0, over a run in which an effect was refused.

    Collecting a forked child's findings is not something this harness can do
    from the parent's side; saying so is. A run that forked is a run this
    report does not cover whole, and an incompleteness is never a pass.
    """
    pack = plant_spawn_pack(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verified(pack, address, a_tree(tmp_path, FORKING_APP))
    assert "worker saw:" in stderr, (stdout, stderr)
    assert code != 0, (stdout, stderr)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert f"{harness.UNJUDGED}: 1" in stdout


# --- 4. an effect on a path no point names leaves coverage incomplete ---------


def plant_a_pack_naming_its_uninterposed_paths(root: Path, *, name: str = "pack") -> Path:
    """The spawn pack, plus the declaration of the paths it does NOT interpose.

    A pack is the one place a library's vocabulary may be written down (article
    4), so it is the pack — never the harness — that says by which other events
    an effect of its kind reaches the world.
    """
    directory = plant_spawn_pack(root, name=name)
    manifest_file = directory / manifest.MANIFEST_FILE
    manifest_file.write_text(
        manifest_file.read_text(encoding="utf-8")
        + f'{harness.UNINTERPOSED} = ["os.posix_spawn", "os.exec"]\n',
        encoding="utf-8",
    )
    return directory


def an_alternate_path_tree(root: Path) -> Path:
    """A program that spawns twice: once through the interposed call, once past it."""
    return a_tree(
        root,
        "import os\n"
        "import subprocess\n"
        "\n"
        "subprocess.run(['true'], check=True)\n"
        "pid = os.posix_spawn('/bin/sh', ['/bin/sh', '-c', 'exit 0'], os.environ)\n"
        "print('second process status:', os.waitpid(pid, 0)[1], flush=True)\n",
    )


def test_an_effect_that_reached_the_world_past_every_point_is_not_a_pass(
    tmp_path: Path,
) -> None:
    """P1-3. Two processes ran, one decision covered one of them, and the run said 0.

    The second creation raises an event no point names, so it was dropped and
    the point's verdict — earned by the first — was published as if it were the
    whole of the run. `docs/PACKS.md` claims « every effect of a KIND a
    designated pack names », and one call shape of that kind reaching the world
    unobserved makes the coverage of that claim incomplete.

    **And the second process still runs.** The limit that instrumentation can
    miss a call is documented and stays true; what changes is that the report
    stops pretending it did not happen. A verifier that aborted the call would
    be the confinement mechanism article 2 says this software is not.
    """
    pack = plant_a_pack_naming_its_uninterposed_paths(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verified(pack, address, an_alternate_path_tree(tmp_path))
    assert "second process status: 0" in stderr, (stdout, stderr)
    assert code != 0, (stdout, stderr)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert f"{harness.UNJUDGED}: 1" in stdout


def test_the_shipped_subprocess_pack_names_the_paths_it_does_not_interpose() -> None:
    """The declaration is the shipped pack's, not a fixture's.

    `src/sayfirst_cli/packs/subprocess` interposes one attribute, and the
    interpreter offers several other ways to create a process. Naming them is
    what lets the verifier count an effect it could not judge instead of
    dropping it.
    """
    shipped = Path(__file__).resolve().parents[1] / "src/sayfirst_cli/packs/subprocess"
    declared = harness.uninterposed_events(manifest.read_pack(shipped))
    named = {event for events in declared.values() for event in events}
    assert "os.posix_spawn" in named, sorted(named)
    assert len(named) >= 3, sorted(named)
    assert "subprocess.Popen" not in named, "a point's own event is interposed, not missed"


# --- 5. a record consumed for one effect must not bury another ----------------

#: A second capability, so that two consultations of one chain ask different
#: questions of it — which is what two threads of one program do.
READING = "file.read"


def an_effect_entry(capability: str, sequence: int) -> Mapping[str, object]:
    """One recorded allow of this execution, at a chosen position in the chain."""
    return recorded_effect_page(capability, sequence=sequence)["entries"][0]


def a_page_of(entries, *, from_sequence: int, next_from: int | None = None) -> dict[str, object]:
    """The page a daemon serves for a read from `from_sequence`, holding those entries."""
    page = recorded_effect_page("example.effect", from_sequence=from_sequence)
    kept = [dict(entry) for entry in entries if int(entry["sequence"]) >= from_sequence]
    page["entries"] = kept
    page["to_sequence"] = kept[-1]["sequence"] if kept else None
    page["next_from"] = next_from
    return page


class OnePageConnection:
    """A chain that answers every read from one fixed list of entries.

    A double and nothing else: it holds no policy, verifies nothing and decides
    nothing. What it gives a test is the one thing a canned daemon cannot — a
    chain whose whole content is known, so that « this record was still there »
    is an assertion rather than a hope.
    """

    server_credential = SimpleNamespace(uid=os.getuid())
    expected_uid = os.getuid()
    verified = True

    def __init__(self, entries) -> None:
        self.entries = list(entries)
        self.reads = 0

    def reconnect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def read_evidence(self, scope: str, at: int, size: int):
        self.reads += 1
        return Answered(a_page_of(self.entries, from_sequence=at), CONTRACT_GENERATION)


def test_a_record_consumed_out_of_order_leaves_an_earlier_one_reachable(
    tmp_path: Path,
) -> None:
    """F5. One cursor for every thread and every capability spends what it skips.

    Both records are in the chain before either consultation. The chain is
    written in decision order and a program runs in execution order, and the
    two are not the same order: a thread granted the earlier record can reach
    its own effect after a thread granted the later one. Advancing one cursor
    past the earlier record makes it permanently unreachable, and the effect it
    covers is then reported as a finding — `ungoverned` — against a decision
    that is sitting in the chain.

    What is spent is what was USED, never what was stepped over.
    """
    connection = OnePageConnection([an_effect_entry(READING, 1), an_effect_entry(SPAWN, 2)])
    chain = harness.Chain(connection, "local", 0)
    later = harness._consulted(chain, SPAWN)
    earlier = harness._consulted(chain, READING)
    assert later.matched == 2, later
    assert earlier.matched == 1, earlier


def test_one_record_still_answers_for_one_effect_only(tmp_path: Path) -> None:
    """The anti-vacuity of the test above: a spent record is spent.

    « Keep every record reachable » would satisfy the rule above and make one
    recorded allow answer for every effect of its kind for ever, which is the
    opposite defect and a worse one.
    """
    connection = OnePageConnection([an_effect_entry(SPAWN, 1)])
    chain = harness.Chain(connection, "local", 0)
    assert harness._consulted(chain, SPAWN).matched == 1
    assert harness._consulted(chain, SPAWN).matched is None


# --- 6. a walk that was interrupted establishes no absence -------------------


def armed_watch() -> harness.Watch:
    """A watch as it stands while the program's own code is running."""
    watch = harness.Watch()
    watch.armed = watch.started = watch.ever_started = True
    return watch


class InterruptedConnection(OnePageConnection):
    """A chain that answers the first page, promises a second, and then cannot.

    The promise is the whole of it: the page itself says the walk is not over,
    so « no matching record was found » is a statement about the part that was
    read and about nothing else.
    """

    def read_evidence(self, scope: str, at: int, size: int):
        self.reads += 1
        if at == 1:
            return Answered(
                a_page_of(self.entries, from_sequence=at, next_from=2), CONTRACT_GENERATION
            )
        return reads.unreadable(ValueError("the second evidence page is unavailable"))


def test_an_interrupted_walk_is_not_an_absence_and_is_not_a_finding() -> None:
    """F6. Some pages read, the walk not finished, and a negative finding published.

    `read_something` says a read was answered; it does not say the chain was
    read to its end. With a continuation the client could not follow, a
    matching record on the unread page is indistinguishable from no record at
    all — and `ungoverned` is a finding this client made, which is the one
    thing incomplete information cannot support.

    The effect is still aborted: what may not be claimed is the finding, not
    the caution.
    """
    pack = manifest.Point(
        module="subprocess",
        attribute="Popen",
        capability=SPAWN,
        digest=("args",),
        audit_event="subprocess.Popen",
    )
    item = harness.Watched("process-effects", pack)
    chain = harness.Chain(InterruptedConnection([an_effect_entry(READING, 1)]), "local", 0)
    with pytest.raises(RuntimeError) as aborted:
        harness._judge(chain, item, armed_watch())
    assert harness.UNGOVERNED not in str(aborted.value), str(aborted.value)
    assert item.refused is False, "a negative finding was published on an unfinished walk"
    assert item.verdict != harness.UNGOVERNED
    assert item.unjudged == 1, item.to_document()


def test_the_command_itself_reports_no_finding_over_an_unfinished_walk(tmp_path: Path) -> None:
    """F6 again, through the shipped command, because the exit code is the claim.

    The daemon answers the first page, promises a second and then serves
    something this client cannot read. That is not « the chain could not be
    read » — a page WAS read — and it is not an absence either. The run carries
    the incompleteness and answers 7, and the effect is aborted: the marker is
    what says the abort happened before the spawn rather than after it.

    The third document is malformed rather than a status the canned daemon
    cannot vary per answer; either way it is a read that arrived and is not an
    answer, which is the fact this case turns on.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-effect-happened"
    unfinished = recorded_effect_page(READING, next_from=2)
    unreadable = {"entries": "not a page this client reads"}
    routes = {"/scopes/": (200, [no_evidence_page(), unfinished, unreadable])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verified(pack, address, a_marking_tree(tmp_path, marker))
    assert code != 0, (stdout, stderr)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert f"ungoverned {POINT}" not in stdout, "a finding was made on an unfinished walk"
    assert f"{harness.UNJUDGED}: 1" in stdout
    assert not marker.exists(), "the effect happened although nothing was established about it"


# --- 7. a report that never arrives asserts nothing --------------------------

#: How long this test waits before calling the run hung. The command's own
#: bound is `verify.HARNESS_TIMEOUT`, fifteen minutes, which is a bound and not
#: a test: a watchdog of its length would make the red run of this test
#: indistinguishable from a suite that had stopped. Generous against a loaded
#: machine, and two orders of magnitude under the bound it stands in for.
WATCHDOG = 45.0


def test_a_target_holding_an_executor_still_reaches_its_own_report(tmp_path: Path) -> None:
    """F8. The interpreter wakes idle workers before joining; this harness did not.

    `ThreadPoolExecutor` parks its workers on a queue and registers, through
    `threading._register_atexit`, the callback that wakes them. The interpreter
    runs those callbacks BEFORE it joins non-daemon threads. This harness
    joined first and never reached the shutdown that would have woken them, so
    a program whose library holds an executor — the ordinary shape of the
    runtimes this chain exists to instrument — finished its work, returned, and
    then hung until the command's fifteen-minute bound.

    A verification that does not end writes no report, and a report that never
    arrives asserts nothing: this is the liveness half of the same rule.
    """
    tree = a_tree(
        tmp_path,
        "from pool_library import pool\n\npool.submit(len, 'x').result()\nprint('main finished')\n",
    )
    (tree / "pool_library.py").write_text(
        "from concurrent.futures import ThreadPoolExecutor\n\npool = ThreadPoolExecutor(1)\n",
        encoding="utf-8",
    )
    pack = plant_spawn_pack(tmp_path)
    routes = {"/scopes/": (200, no_evidence_page())}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        finished = subprocess.run(
            [
                str(CONSOLE_SCRIPT),
                "instrument",
                "verify",
                "--pack",
                str(pack),
                "--socket",
                str(address),
                "--scope",
                "local",
                "--ungoverned",
                "--",
                "app.py",
            ],
            cwd=str(tree),
            capture_output=True,
            text=True,
            timeout=WATCHDOG,
        )
    assert "main finished" in finished.stderr, (finished.stdout, finished.stderr)
    assert f"not-exercised {POINT} events=0" in finished.stdout
    assert finished.returncode == exit_codes.EXIT_COULD_NOT_CHECK, finished.stdout
