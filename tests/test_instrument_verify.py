# SPDX-License-Identifier: Apache-2.0
"""What `sayfirst instrument verify` proves, and the verdict it never renders green.

Every run here goes through the shipped console script, for the reason
`governed_programs.py` gives and one more of its own: the verifier's whole
mechanism is a subprocess under an audit hook that can never be removed, so a
verification run inside the test process would leave that hook behind for the
rest of the session.

The chain-driven cases run `--ungoverned`. That is not a shortcut — it is the
point of the layer: the verifier reads the interpreter's audit events and the
daemon's chain, and nothing else, so how the decision came to be in the chain
is not its question. The one case that needs a real boundary in front of the
program uses the contract's fake, whose evidence pages are placeholders by its
own docstring, so it proves the hand-off and the report's shape and says so;
the chain against a real daemon is the control plane's e2e.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import py_compile
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from canned_daemon import answering_by_path
from documents import foreign_generation_page, no_evidence_page, problem, recorded_effect_page
from governed_programs import (
    FIRST_ARGUMENT_INTERPOSE,
    SPAWNING_APP,
    instrument,
    plant_pack,
    plant_spawn_pack,
)
from sayfirst_contract_stub.stub import Stub
from sayfirst_contract_stub.stub_http import serve

from sayfirst_cli import exit_codes
from sayfirst_cli.instrument import commands, harness, launch, manifest
from sayfirst_cli.instrument import verify as verify_command

#: The capability the spawn pack declares, which is what the chain must carry.
SPAWN = "process.spawn"


def a_spawning_tree(root: Path) -> Path:
    """A program that spawns one process and catches nothing."""
    tree = root / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    return tree


def a_quiet_tree(root: Path, *, body: str = "print('quiet')\n") -> Path:
    """A program that walks no governed path at all."""
    tree = root / "quiet"
    tree.mkdir()
    (tree / "app.py").write_text(body, encoding="utf-8")
    return tree


def a_marking_tree(root: Path, marker: Path) -> Path:
    """A program whose spawned process leaves a file behind, or does not.

    Both halves of the abort claim are read off this one target: with a
    decision in the chain the file appears, and without one it does not. A
    hook that raised after the effect would satisfy every other assertion in
    either test.
    """
    return a_quiet_tree(
        root,
        body=f"import subprocess\n\nsubprocess.run(['touch', {str(marker)!r}], check=True)\n",
    )


def verify(*argv: str, cwd: Path) -> tuple[int, str, str]:
    """Run the real command the way a person runs it."""
    finished = instrument("verify", *argv, cwd=cwd)
    return finished.returncode, finished.stdout, finished.stderr


def in_process(*argv: str) -> tuple[int, str, str]:
    """For the refusals that spawn nothing: no interpreter starts, so no hook is installed.

    Safe only because these invocations are refused BEFORE the harness runs —
    an audit hook installed in this process could never be taken out again.
    """
    out, err = io.StringIO(), io.StringIO()
    code = commands.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_an_effect_the_chain_decided_is_governed(tmp_path: Path) -> None:
    """The whole claim, in one run: one spawn, one recorded allow, exit 0.

    The first page the daemon serves is empty — that is the read the harness
    takes its starting position from — and the effect appears on the page it
    serves afterwards, which is how a chain written during a run behaves.

    The spawned process leaves a file behind, and the file is there: the twin
    of the abort test's assertion that it is not. A verifier that stopped every
    effect would pass that one and fail this.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-effect-happened"
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_marking_tree(tmp_path, marker),
        )
    assert code == 0, (stdout, stderr)
    assert f"governed process-effects subprocess.Popen {SPAWN} events=1" in stdout
    assert "ungoverned" not in stdout
    assert "inspected: process-effects" in stdout
    assert "target exit: 0" in stdout
    assert marker.exists(), "the spawn was reported as governed and never happened"


def test_an_effect_no_decision_preceded_is_ungoverned_and_does_not_happen(tmp_path: Path) -> None:
    """The chain holds nothing, so the hook aborts the spawn and the target dies.

    Exit 6 is a finding this client made, never a denial the plane gave
    (`exit_codes.py`), and the sentence the hook raised names the capability
    and the event so that a reader knows which effect was stopped.

    **And the effect did not happen.** The target spawns a process whose whole
    job is to leave a file behind, and the file is not there. Without that
    assertion every line below is equally true of a hook that raised AFTER the
    spawn — and « it aborts the effect rather than reporting afterwards that it
    had already happened » is this layer's central claim.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-effect-happened"
    tree = a_marking_tree(tmp_path, marker)
    routes = {"/scopes/": (200, no_evidence_page())}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert code != exit_codes.EXIT_DENY
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=0" in stdout
    assert f"ungoverned effect: {SPAWN} (subprocess.Popen)" in stderr
    assert not marker.exists(), "the spawn was reported as ungoverned and still happened"


@pytest.mark.parametrize("page", [no_evidence_page(), recorded_effect_page(SPAWN)])
def test_a_path_never_walked_is_said_and_never_counted_as_a_pass(
    tmp_path: Path, page: dict[str, object]
) -> None:
    """Article 2: `not-exercised` is a third value, and it is not a green one.

    The chain is irrelevant here, which is why both pages are run: a page
    carrying a decision does not make a path the program never walked proven.
    """
    pack = plant_spawn_pack(tmp_path)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, page)}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_quiet_tree(tmp_path),
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert code != 0
    assert f"not-exercised process-effects subprocess.Popen {SPAWN} events=0" in stdout
    assert "governed process-effects" not in stdout


def test_inspected_names_every_pack_that_was_designated(tmp_path: Path) -> None:
    """Article 9's anti-vacuity demand: a verifier that inspected nothing is red.

    The set is read off the points the harness actually watched for, not off
    the command line, so a pack that contributed nothing could not appear in
    it — which is what the public gate asserts against the shipped set.
    """
    first = plant_spawn_pack(tmp_path, name="first")
    second = plant_pack(
        tmp_path,
        name="second",
        module="shutil",
        attribute="rmtree",
        capability="file.remove",
    )
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(first),
            "--pack",
            str(second),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_quiet_tree(tmp_path),
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert "inspected: process-effects second" in stdout
    assert "not-exercised second shutil.rmtree file.remove events=0" in stdout


def test_the_verdict_comes_from_the_chain_and_not_from_how_the_run_was_made(
    tmp_path: Path,
) -> None:
    """« Verifier ← everything »: the verifier does not care how the decision got there.

    This daemon answers reads and nothing else — it has no route for an ask at
    all — and the program runs with nothing in front of it, so no question was
    put by anybody during this run. The verdict is still `governed`, because a
    record in the chain is what the proof is made of. A verifier that needed
    the engine's cooperation to say `governed` would be trusting the thing it
    is proving.
    """
    pack = plant_spawn_pack(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    assert code == 0, (stdout, stderr)
    assert stdout.splitlines() == [
        f"governed process-effects subprocess.Popen {SPAWN} events=1",
        "inspected: process-effects",
        "target exit: 0",
    ]


def test_an_effect_recorded_as_denied_does_not_govern_it(tmp_path: Path) -> None:
    """The outcome is read, never assumed: only `allow` is a decision to act.

    Without this the match would be « a record of this capability exists »,
    which a refused effect satisfies as well as an allowed one — and reporting
    that as `governed` would be the false all-clear this chain exists against.

    The record lies INSIDE the window, which is the whole of what this test
    needed and did not have: served on one page for every read, the head walk
    consumed it and the cursor already excluded it, so the outcome clause was
    never reached and the test passed for a reason that had nothing to do with
    the outcome. Measured: with `and body.get("outcome") == ALLOW` deleted from
    `harness.py`, this test now fails (`events=1`, `governed`, exit 0) — the
    mutation result is in the report.
    """
    pack = plant_spawn_pack(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN, outcome="deny")])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert f"ungoverned process-effects subprocess.Popen {SPAWN}" in stdout


def test_the_json_form_carries_the_report_and_what_was_verified(tmp_path: Path) -> None:
    """The envelope every other read of this client writes, with the report as its result."""
    pack = plant_spawn_pack(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--json",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    assert code == 0, (stdout, stderr)
    envelope = json.loads(stdout)
    assert envelope["verification"]["verified"] is True
    report = envelope["result"]
    assert report["inspected"] == ["process-effects"]
    assert report["packs"] == ["process-effects"]
    assert report["start_sequence"] == 1
    assert report["target_exit"] == 0
    assert report["points"] == [
        {
            "attribute": "Popen",
            "audit_event": "subprocess.Popen",
            "capability": SPAWN,
            "events": 1,
            # Empty, and present: the count says how much this run could not
            # judge and this says why, so a run with nothing outstanding
            # publishes an empty list rather than leaving a reader to infer one.
            "incomplete": [],
            "module": "subprocess",
            "pack": "process-effects",
            "unjudged": 0,
            "verdict": "governed",
        }
    ]


def test_the_governed_hand_off_runs_the_program_through_the_engine(tmp_path: Path) -> None:
    """Governed mode is the launcher's own hand-off, proven through the contract's fake.

    What this establishes is the hand-off and the report's shape: the program
    ran with the boundary and the engine in front of it, its own ending was
    captured rather than propagated, and the findings came back. What it does
    NOT establish is a chain — the fake's own docstring says its evidence pages
    are placeholders — so the verdict here is `not-exercised` and the exit is
    7, which is the honest answer for a run against a daemon that records
    nothing. The chain-plus-boundary proof is the control plane's e2e.
    """
    pack = plant_spawn_pack(tmp_path)
    tree = a_quiet_tree(tmp_path, body="import sys\n\nprint('ran')\nsys.exit(5)\n")
    with serve(Stub("allow"), tmp_path / "d.sock") as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert f"not-exercised process-effects subprocess.Popen {SPAWN} events=0" in stdout
    # The program's own ending is a fact in the report, never this command's code.
    assert "target exit: 5" in stdout
    assert "ran" in stderr
    assert "Traceback" not in stderr


def test_a_pack_that_does_not_read_is_a_misuse_before_anything_is_spawned(tmp_path: Path) -> None:
    """The same rule `run` obeys, with the path as it was typed."""
    absent = tmp_path / "absent"
    code, out, err = in_process(
        "verify",
        "--pack",
        str(absent),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert err.startswith(f"{absent}: ")
    assert "pack.toml" in err
    assert out == ""


def test_a_manifest_nested_deeper_than_the_reader_parses_is_a_misuse(tmp_path: Path) -> None:
    """The third of the three verbs that read a pack, on the same refusal.

    `verify` reads every pack before a second interpreter is started, so a
    manifest no parser descends is this invocation's mistake — 64 — and never
    the exit 1 the interpreter's own `RecursionError` produced, which this
    client publishes as « the control plane answered deny ».
    """
    pack = plant_spawn_pack(tmp_path)
    (pack / "pack.toml").write_text("x = " + "[" * 3000 + "]" * 3000 + "\n", encoding="utf-8")
    code, out, err = in_process(
        "verify",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert out == ""
    assert "nests deeper than this reader parses" in err


def test_a_system_profile_that_names_no_account_is_a_misuse(tmp_path: Path) -> None:
    """A profile that cannot say what it must verify is refused before the spawn."""
    pack = plant_spawn_pack(tmp_path)
    code, _, err = in_process(
        "verify",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--mode",
        "system",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_MISUSE
    assert "names the account" in err


def test_a_run_with_no_program_after_the_separator_is_the_invocations_own_code(
    tmp_path: Path,
) -> None:
    """64, the code `instrument run` gives the same mistake, and not 4.

    The harness refuses the invocation and writes no findings. Reporting that
    as « could not ask » would make one mistake read two ways depending on
    which verb produced it, which is the collision `exit_codes.py` names.
    """
    pack = plant_spawn_pack(tmp_path)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            cwd=tmp_path,
        )
    assert code == exit_codes.EXIT_MISUSE, (stdout, stderr)
    assert code != exit_codes.EXIT_DENY
    assert "needs a program to run after `--`" in stderr
    assert "governed" not in stdout


def test_a_harness_that_wrote_no_findings_is_never_a_verdict(tmp_path: Path, monkeypatch) -> None:
    """No report is « could not ask », with what the harness said, and never green.

    Pointed at a module that cannot be executed, so the second interpreter ends
    before it has read a pack — the shape a harness killed by the host, or one
    whose interpreter could not start, would take.
    """
    pack = plant_spawn_pack(tmp_path)
    monkeypatch.setattr(verify_command, "HARNESS_MODULE", "sayfirst_cli.instrument")
    code, out, err = in_process(
        "verify",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "d.sock"),
        "--scope",
        "local",
        "--ungoverned",
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert code != 0
    assert "no findings" in err
    assert "cannot be directly executed" in err
    assert out == ""


def test_the_help_names_the_verb_and_its_options() -> None:
    """Article 2: a help text is a claim about what exists, and this one now exists."""
    text = commands.build_parser().format_help()
    assert "verify" in text
    assert "not yet" not in text


# --- Whose act was it -----------------------------------------------------------

#: The capability a pack declares over the interpreter's own file-reading event.
#: Its segments borrow nothing from the module or the attribute, which
#: `manifest.py` requires of every capability (article 4).
READING = "file.reading"


def a_pack_watching_the_interpreters_own_reads(root: Path, *, name: str = "watcher") -> Path:
    """A pack whose declared event the harness itself raises, over and over.

    This is the pack that found the defect: the interpreter reports the chain
    reads, the report write and its own reading of the program's file with the
    same event, so a harness that judged its own acts as the program's could
    neither conclude nor write its findings.
    """
    return plant_pack(
        root,
        name=name,
        module="builtins",
        attribute="open",
        capability=READING,
        interpose=FIRST_ARGUMENT_INTERPOSE,
        audit_event="open",
    )


def a_tree_that_reads_another_file(root: Path) -> Path:
    """A program whose one effect is reading a file that is not itself."""
    tree = root / "reader"
    tree.mkdir()
    (tree / "beside.txt").write_text("read me\n", encoding="utf-8")
    (tree / "app.py").write_text(
        "with open('beside.txt', encoding='utf-8') as opened:\n    opened.read()\n",
        encoding="utf-8",
    )
    return tree


def test_the_harnesss_own_acts_are_not_the_programs_and_the_findings_survive(
    tmp_path: Path,
) -> None:
    """The program's own read is judged; everything the harness does is not.

    Measured as the defect: the consultation fired before the program was even
    read, fired again inside the report write, and the run answered exit 4 with
    the word `ungoverned` nowhere on either stream — a true finding converted
    into « could not check », which is article 2's failure in the other
    direction.
    """
    pack = a_pack_watching_the_interpreters_own_reads(tmp_path)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_tree_that_reads_another_file(tmp_path),
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert f"ungoverned watcher builtins.open {READING} events=0" in stdout
    assert f"ungoverned effect: {READING} (open)" in stderr
    # The findings were written: a report that lost itself to the abort it
    # caused would have answered 4 with nothing said about the program.
    assert "inspected: watcher" in stdout
    assert "no findings" not in stderr


def test_the_events_a_watched_program_produces_are_counted_and_no_others(
    tmp_path: Path,
) -> None:
    """Anti-vacuity for the exclusions: the count is the program's own acts, exactly.

    The chain carries five records where the program reads one file, so a
    single leaked act of the harness's or the launcher's own — the interpreter
    reading the program, `runpy` importing what it needs on first use, the
    chain reads, the report write — shows up as `events` greater than one
    rather than as a run that happens to pass. It is the guard over
    `launch.PREPARED`, which is an implementation detail of the interpreter.
    """
    pack = a_pack_watching_the_interpreters_own_reads(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(READING, count=5)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_tree_that_reads_another_file(tmp_path),
        )
    assert code == 0, (stdout, stderr)
    assert f"governed watcher builtins.open {READING} events=1" in stdout


def test_the_engines_load_of_a_packs_execution_module_is_not_the_programs_act(
    tmp_path: Path,
) -> None:
    """Governed mode, with the pack whose event the engine's own load raises.

    The hook is installed before the engine — an interpreter that could be
    asked to forget a hook would make the proof optional — so what draws the
    line is the ARMING, which the launcher does at the last instant, after it
    has loaded every execution module and resolved the target. Without that,
    the engine's read of `interpose.py` was judged as the program's first
    effect and the run came back as a misuse.
    """
    pack = a_pack_watching_the_interpreters_own_reads(tmp_path)
    tree = a_quiet_tree(tmp_path, body="import sys\n\nsys.exit(0)\n")
    with serve(Stub("allow"), tmp_path / "d.sock") as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert code != exit_codes.EXIT_MISUSE
    assert f"not-exercised watcher builtins.open {READING} events=0" in stdout
    assert "did not load" not in stderr
    assert "target exit: 0" in stdout


def test_the_watch_answers_whose_act_an_event_was_and_nothing_else() -> None:
    """The four rules, each read off `Watch` directly rather than through a run.

    A run can only show them together, and two of them are cheap to leave
    broken in a way a run still passes: without the disarming the report write
    and the traceback are judged as the program's, which a run survives by
    being sixty times slower rather than by being red.
    """
    watch = harness.Watch()
    started = compile("pass", __file__, "exec")
    # Before the launcher arms it, nothing at all is the program's act.
    assert watch.whose(("anything",)) == harness.THE_HAND_OFFS
    watch.arm((__file__,), (__file__,), ())
    # Armed, but the hand-off is still locating and reading the program: the
    # gate is shut and nothing is judged yet. This is the window the start-file
    # exclusion exists for, and the gate is what covers it — every event here
    # is the hand-off's, whatever it names.
    assert not watch.judging
    assert watch.whose(("some/other/file",)) == harness.THE_HAND_OFFS
    assert watch.whose((__file__,)) == harness.THE_HAND_OFFS
    # A code object for the program's file, carried beside something else, is
    # the import system writing that code down and not the interpreter running
    # it. Measured as a defect: it opened the gate on the cache write.
    watch.opening((started, 4))
    assert not watch.judging
    # The code object alone is the program beginning.
    watch.opening((started,))
    assert watch.judging
    assert watch.whose(("some/other/file",)) == harness.THE_PROGRAMS
    # And the converse of the exclusion, which nothing exercised until the
    # count existed: the same names, once the program has started, are neither
    # the hand-off's act nor anything this proof can judge. They are counted.
    assert watch.whose((__file__,)) == harness.NOT_JUDGED
    assert watch.whose((0, __file__, "r")) == harness.NOT_JUDGED
    with watch.ours():
        assert watch.whose(("some/other/file",)) == harness.THE_HAND_OFFS
    assert watch.whose(("some/other/file",)) == harness.THE_PROGRAMS
    watch.disarm()
    assert not watch.judging
    assert watch.whose(("some/other/file",)) == harness.THE_HAND_OFFS


def test_the_three_answers_are_three_and_none_of_them_is_a_verdict() -> None:
    """The vocabulary stays three words wide, and the count is not a fourth.

    `unjudged` is a number of events and `NOT_JUDGED` is an answer about one
    event; neither may reach the report as a verdict, because `verify` renders
    a point on the strength of its verdict being one of the closed three.
    """
    answers = {harness.THE_PROGRAMS, harness.THE_HAND_OFFS, harness.NOT_JUDGED}
    assert len(answers) == 3
    assert answers.isdisjoint(harness.VERDICTS)
    assert harness.UNJUDGED not in harness.VERDICTS
    assert harness.VERDICTS == ("governed", "ungoverned", "not-exercised")


def test_a_gate_that_never_opens_judges_nothing_at_all() -> None:
    """A code object no resolved file matches leaves the gate shut for ever.

    Nothing is then judged, and the run must not conclude an absence it never
    established: `_prove` answers « the verifier never saw the program's own
    code start » and exit 4 rather than `not-exercised`
    (`test_a_gate_that_never_opened_says_so_and_reports_no_verdict` holds that
    end to end). This is the half of it that belongs to the watch.
    """
    watch = harness.Watch()
    watch.arm(("/nowhere/that/was/resolved.py",), ("/nowhere/that/was/resolved.py",), ())
    watch.opening((compile("pass", __file__, "exec"),))
    assert not watch.judging
    assert watch.whose(("anything at all",)) == harness.THE_HAND_OFFS
    # And a target the launcher could not name a file for at all.
    silent = harness.Watch()
    silent.arm((), (), ())
    silent.opening((compile("pass", __file__, "exec"),))
    assert not silent.judging


# --- An exclusion is never silent -----------------------------------------------


def a_tree_that_reads_a_file_and_then_its_own(root: Path) -> Path:
    """A program whose two effects differ in one argument.

    The first reads a file beside it; the second reads the file the program was
    started from. One decision in the chain covers the first, and the second is
    the shape the exclusion used to drop in silence — so a run that reports
    only the first has flattered the program by exactly the effect the chain
    never decided.
    """
    tree = root / "own-file"
    tree.mkdir()
    (tree / "beside.txt").write_text("read me\n", encoding="utf-8")
    application = tree / "app.py"
    application.write_text(
        "with open('beside.txt', encoding='utf-8') as opened:\n"
        "    opened.read()\n"
        f"with open({str(application.resolve())!r}, encoding='utf-8') as mine:\n"
        "    mine.read()\n",
        encoding="utf-8",
    )
    return tree


def test_an_effect_that_names_the_programs_own_file_is_counted_and_never_a_pass(
    tmp_path: Path,
) -> None:
    """Exit 7 and `unjudged: 1`, where this answered exit 0 and `governed`.

    Measured through the shipped console script before this rule: two programs
    differing in one argument — `beside.txt` and the program's own path — came
    back exit 6 `ungoverned` and exit 0 `governed` respectively, the second
    with an effect that was not judged, not aborted, not counted and not
    mentioned.

    The verdict stays honest about the event that WAS judged, which is why it
    still reads `governed`: a verdict rewritten to `not-exercised` would deny
    the judged event and one rewritten to `ungoverned` would publish a finding
    nobody made. The count is what says the rest, and the exit code is what
    refuses the pass.
    """
    pack = a_pack_watching_the_interpreters_own_reads(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(READING, count=1)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_tree_that_reads_a_file_and_then_its_own(tmp_path),
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert code != 0
    assert f"governed watcher builtins.open {READING} events=1" in stdout
    assert f"unjudged: 1 watcher builtins.open {READING}" in stdout
    assert "could not judge it and is not a pass" in stdout
    # The program itself ran to its end: the count is not an abort.
    assert "target exit: 0" in stdout


def a_tree_that_spawns_itself(root: Path, marker: Path) -> Path:
    """A program that spawns something ordinary, then spawns its OWN file.

    The second spawn is a real process — the marker proves it ran — and the
    interpreter reports the executable by name, which is how an effect comes to
    name one of the program's own start files while being an effect on the
    world. The shebang is what makes it executable, and `sys.executable` is
    what makes the shebang this interpreter.
    """
    tree = root / "spawns-itself"
    tree.mkdir()
    application = tree / "app.py"
    application.write_text(
        f"#!{sys.executable}\n"
        "import subprocess\n"
        "import sys\n\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'child':\n"
        f"    open({str(marker)!r}, 'w').close()\n"
        "    raise SystemExit(0)\n"
        "subprocess.run(['true'], check=True)\n"
        f"subprocess.run([{str(application.resolve())!r}, 'child'], check=True)\n",
        encoding="utf-8",
    )
    application.chmod(application.stat().st_mode | stat.S_IEXEC)
    return tree


def test_a_spawn_of_the_programs_own_file_is_counted_and_never_a_pass(tmp_path: Path) -> None:
    """The same hole on the spawn pack, where the effect is a whole process.

    Measured before this rule: exit 0, `governed`, `events=1` — with the second
    process actually run, no decision behind it, and the parent finishing
    normally. This is the worst place for it, because `engine.py` says a
    reference bound before the engine ran is not instrumented and that finding
    that gap is the verifier's job.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-child-ran"
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN, count=1)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_tree_that_spawns_itself(tmp_path, marker),
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert code != 0
    assert f"governed process-effects subprocess.Popen {SPAWN} events=1" in stdout
    assert f"unjudged: 1 process-effects subprocess.Popen {SPAWN}" in stdout
    # The effect really happened, which is why a silent exclusion here was the
    # false all-clear and not a rounding error.
    assert marker.exists(), (stdout, stderr)


def test_a_point_with_a_count_and_no_judged_event_is_still_an_absence(tmp_path: Path) -> None:
    """A count does not invent a verdict: with nothing judged it is `not-exercised`.

    Read off `Watched` rather than through a run, because the combination needs
    a program whose ONLY effect names its own start file, and the point of the
    assertion is the rule and not the program: the three words stay closed, and
    the count is carried beside them.
    """
    point = manifest.Point(
        module="example_module",
        attribute="effect",
        capability="example.action",
        digest=("first",),
        audit_event="example_module.effect",
    )
    counted = harness.Watched("planted", point, events=0, unjudged=2)
    assert counted.verdict == harness.NOT_EXERCISED
    assert counted.to_document()[harness.UNJUDGED] == 2
    judged = harness.Watched("planted", point, events=1, unjudged=1)
    assert judged.verdict == harness.GOVERNED
    refused = harness.Watched("planted", point, events=1, refused=True, unjudged=1)
    assert refused.verdict == harness.UNGOVERNED
    # And the exit code is the one place the count changes the answer, in the
    # direction article 2 requires: never over a finding, always over a pass.
    assert verify_command._exit_for([harness.GOVERNED], [0]) == 0
    assert verify_command._exit_for([harness.GOVERNED], [1]) == exit_codes.EXIT_COULD_NOT_CHECK
    assert verify_command._exit_for([harness.UNGOVERNED], [1]) == exit_codes.EXIT_CHECK_FAILED
    assert verify_command._exit_for([harness.NOT_EXERCISED], [1]) == exit_codes.EXIT_COULD_NOT_CHECK


def test_a_report_without_a_count_is_findings_this_client_cannot_read(tmp_path: Path) -> None:
    """The count is required of a report, like the verdict beside it.

    A rendering that read a missing count as zero would turn « these findings
    are not this client's » into a pass on the one field that exists to refuse
    one.
    """
    out, err = io.StringIO(), io.StringIO()
    arguments = argparse.Namespace(json=False)
    point = {
        "verdict": "governed",
        "pack": "p",
        "module": "m",
        "attribute": "a",
        "capability": "x.y",
        "events": 1,
    }
    for doctored in (point, {**point, harness.UNJUDGED: "one"}, {**point, harness.UNJUDGED: -1}):
        code = verify_command._rendered({"points": [doctored]}, arguments, out, err)
        assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert out.getvalue() == ""
    assert err.getvalue().count("not a report this client reads") == 3


# --- An unreadable chain is not a finding ---------------------------------------


def test_a_chain_that_never_answered_is_could_not_read_and_never_a_finding(
    tmp_path: Path,
) -> None:
    """Exit 4, not 6: exit 6 is published as a finding this client MADE.

    The daemon answers the head walk and then every later read in a generation
    this client does not speak — a restart across a generation bump, which
    article 13 makes the transport refuse. « No record exists » and « this
    client could not read the chain » are different facts, and `exit_codes.py`
    exists to keep them apart.
    """
    pack = plant_spawn_pack(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), foreign_generation_page()])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    assert code == exit_codes.EXIT_COULD_NOT_ASK, (stdout, stderr)
    assert code != exit_codes.EXIT_CHECK_FAILED
    assert code != 0
    assert stdout == ""
    assert "ungoverned" not in stderr
    assert "the chain could not be read while the program ran" in stderr
    # The transport's own sentence, carried rather than replaced by one of ours.
    assert "this connection was opened on contract version" in stderr


def test_a_chain_that_answered_and_then_stopped_is_a_finding_with_the_failure_beside_it(
    tmp_path: Path,
) -> None:
    """Some reads answered, so the verdict is made of what WAS read.

    The first consultation read a page and found no record; the chain then went
    away. The absence was established, so the finding stands — and the failure
    is said beside it, because a reader has to be able to see that the chain
    stopped answering while this run was concluding.
    """
    pack = plant_spawn_pack(tmp_path)
    routes = {
        "/scopes/": (200, [no_evidence_page(), no_evidence_page(), foreign_generation_page()])
    }
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=0" in stdout
    assert "the chain was read and then stopped answering" in stderr
    assert "this connection was opened on contract version" in stderr


# --- `--json` answers in the envelope on every path -----------------------------


def a_report_that_will_not_read(root: Path) -> Path:
    """A pack whose run produces findings, for the path that doctors them."""
    return plant_spawn_pack(root)


@pytest.mark.parametrize("as_json", [False, True])
def test_a_verification_that_could_not_be_obtained_answers_in_the_form_asked_for(
    tmp_path: Path, as_json: bool
) -> None:
    """No daemon at the address: exit 4, and under `--json` the problem envelope.

    Every other read of this client writes a problem envelope under `--json`
    (`reads.finish`). A flag whose promise held only when the verification
    concluded would be a flag a machine caller cannot use on exactly the paths
    it has to tell apart. The envelope is on STDOUT here and not on the error
    stream, because the verified program owns the error stream — see
    `test_the_no_answer_envelope_does_not_share_a_stream_with_the_program`.

    The problem is `unreachable` rather than `answer_unreadable`: the harness's
    own account of how it ended says the chain could not be read before the
    program started, and carrying that fact through rather than guessing at it
    from a number is the whole of the side channel.
    """
    pack = plant_spawn_pack(tmp_path)
    code, stdout, stderr = verify(
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--ungoverned",
        *(["--json"] if as_json else []),
        "--",
        "app.py",
        cwd=a_quiet_tree(tmp_path),
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK, (stdout, stderr)
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["problem"]["code"] == "unreachable"
        assert "no findings" in envelope["problem"]["message"]
        assert envelope["verification"] == {
            "server_uid": None,
            "expected": None,
            "verified": False,
        }
        assert "result" not in envelope
    else:
        assert stdout == ""
        assert "no findings" in stderr
        assert "{" not in stderr.replace("{}", "")


@pytest.mark.parametrize("as_json", [False, True])
def test_a_verification_refused_before_it_began_answers_in_the_form_asked_for(
    tmp_path: Path, as_json: bool
) -> None:
    """The other no-findings path: 64, with the envelope when one was asked for."""
    pack = plant_spawn_pack(tmp_path)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            *(["--json"] if as_json else []),
            "--",
            cwd=tmp_path,
        )
    assert code == exit_codes.EXIT_MISUSE, (stdout, stderr)
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["problem"]["code"] == "request_malformed"
        assert "refused before it began" in envelope["problem"]["message"]
    else:
        assert stdout == ""
        assert "refused before it began" in stderr
    # The harness's own sentence reaches the stream either way.
    assert "needs a program to run after `--`" in stderr


@pytest.mark.parametrize("as_json", [False, True])
def test_findings_this_client_cannot_read_are_never_a_verdict(
    tmp_path: Path, monkeypatch, as_json: bool
) -> None:
    """A report that arrived and will not read: exit 7, and never a green one.

    Arranged by pointing the harness at a module that writes no report at all
    and handing this command a doctored one, which is the only way to reach the
    branch: the harness itself cannot produce a report whose verdicts are not
    of the closed vocabulary.
    """
    pack = a_report_that_will_not_read(tmp_path)
    monkeypatch.setattr(verify_command, "HARNESS_MODULE", "sayfirst_cli.instrument")

    doctored = {"points": [{"verdict": "probably-fine", "pack": "p"}], "inspected": ["p"]}
    real_findings = verify_command._findings

    def findings(report: Path):
        return doctored if real_findings(report) is None else real_findings(report)

    monkeypatch.setattr(verify_command, "_findings", findings)
    code, out, err = in_process(
        "verify",
        "--pack",
        str(pack),
        "--socket",
        str(tmp_path / "absent.sock"),
        "--scope",
        "local",
        "--ungoverned",
        *(["--json"] if as_json else []),
        "--",
        "app.py",
    )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert code != 0
    if as_json:
        assert json.loads(out)["problem"]["code"] == "answer_unreadable"
        assert "not a report this client reads" in json.loads(out)["problem"]["message"]
    else:
        assert out == ""
        assert "not a report this client reads" in err


# --- The program is not done when its main returns ------------------------------


def a_tree_that_spawns_from_a_thread(
    root: Path, marker: Path, *, also_now: Path | None = None
) -> Path:
    """A program whose main module returns while a thread of its own spawns later.

    The ordinary shape of a worker: the main module starts a thread and ends.
    The thread is not a daemon, so the interpreter waits for it — and whatever
    it does is still the program's act, however long after the main module
    returned it happens.
    """
    now = "" if also_now is None else f"subprocess.run(['touch', {str(also_now)!r}], check=True)\n"
    return a_quiet_tree(
        root,
        body=(
            "import subprocess\n"
            "import threading\n"
            "import time\n"
            "\n"
            "\n"
            "def later():\n"
            "    time.sleep(0.6)\n"
            f"    subprocess.run(['touch', {str(marker)!r}], check=True)\n"
            "\n"
            "\n"
            "threading.Thread(target=later).start()\n"
            f"{now}"
        ),
    )


def test_an_effect_a_thread_makes_after_main_returns_is_judged_and_aborted(
    tmp_path: Path,
) -> None:
    """The watch stays armed until the PROGRAM is done, not until the hand-off returns.

    Measured as the defect: the thread's spawn landed after `disarm`, so it was
    neither judged nor aborted and the run answered `not-exercised` / exit 7
    while the process it spawned ran to completion — an absence rendered over
    an effect that happened, which is the false all-clear article 2 forbids.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "the-thread-spawned"
    tree = a_tree_that_spawns_from_a_thread(tmp_path, marker)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert code != 0
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=0" in stdout
    assert f"ungoverned effect: {SPAWN} (subprocess.Popen)" in stderr
    # The main module returned cleanly; the verdict is not its ending.
    assert "target exit: 0" in stdout
    assert not marker.exists(), "the thread's spawn was judged ungoverned and still happened"


def test_a_second_effect_the_first_decision_does_not_cover_is_found(tmp_path: Path) -> None:
    """The measured false all-clear, held as a test: one record, two effects.

    The main thread spawns and the chain accounts for it; a thread spawns again
    afterwards and nothing accounts for that. Before the watch waited for the
    program's own threads this answered **exit 0 and `governed`** with both
    processes run — a decision for one effect reported as governance of two.
    """
    pack = plant_spawn_pack(tmp_path)
    decided = tmp_path / "the-decided-spawn"
    undecided = tmp_path / "the-undecided-spawn"
    tree = a_tree_that_spawns_from_a_thread(tmp_path, undecided, also_now=decided)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN, count=1)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert code != 0
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=1" in stdout
    assert decided.exists(), "the decided spawn was refused"
    assert not undecided.exists(), "the undecided spawn happened"


# --- The hand-off's own files, for the `-m` form --------------------------------


def a_module_that_reads_another_file(root: Path, *, package: bool) -> Path:
    """A one-read program named to `-m`, as a plain module or as a package."""
    tree = root / ("pkg-form" if package else "module-form")
    tree.mkdir()
    (tree / "beside.txt").write_text("read me\n", encoding="utf-8")
    body = "with open('beside.txt', encoding='utf-8') as opened:\n    opened.read()\n"
    if package:
        inside = tree / "mypkg"
        inside.mkdir()
        (inside / "__init__.py").write_text("", encoding="utf-8")
        (inside / "__main__.py").write_text(body, encoding="utf-8")
    else:
        (tree / "solo.py").write_text(body, encoding="utf-8")
    return tree


@pytest.mark.parametrize("package", [False, True])
@pytest.mark.parametrize("warm", [False, True])
def test_the_module_form_counts_the_programs_own_events_and_no_others(
    tmp_path: Path, package: bool, warm: bool
) -> None:
    """A `-m` run of a one-read program is one event, cold and warm alike.

    Measured before this: the `-m` forms counted **4** events cold and **2**
    warm, against the script form's 1 — the import system's cache read, the
    name it derives to write that cache, and a write through a bare descriptor.
    With a one-record chain, what a daemon that decided one effect holds, the
    same run therefore answered **exit 6, `ungoverned`**: a finding published
    about a program that did nothing wrong, with the raise aborting its own
    start. Both counts are 1 now, so a single record governs the run.

    Cold and warm are both run because they are different code paths in the
    import system — a miss compiles and writes, a hit loads — and the first
    version of the fix passed warm while leaking two events cold.
    """
    pack = a_pack_watching_the_interpreters_own_reads(tmp_path)
    tree = a_module_that_reads_another_file(tmp_path, package=package)
    target = ["-m", "mypkg" if package else "solo"]
    if warm:
        # The bytecode cache as a second run would find it, written by an
        # ordinary interpreter rather than by anything under test.
        subprocess.run(
            [sys.executable, *target], cwd=str(tree), capture_output=True, timeout=120, check=True
        )
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(READING, count=1)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            *target,
            cwd=tree,
        )
    assert code == 0, (stdout, stderr)
    assert f"governed watcher builtins.open {READING} events=1" in stdout


def test_the_launcher_names_where_the_import_system_keeps_a_cache() -> None:
    """The hand-off's own files include each source AND its bytecode cache.

    Held here rather than through a run, and deliberately: the event counts
    above do not depend on this rule — the gate already excludes everything
    before the program's own code, and dropping this clause leaves them at 1
    (measured). It is kept as the rule that is true whenever it fires rather
    than only during a hand-off, so it does not rest on the gate's shape
    holding; and a rule no test exercises is a rule nobody will notice
    breaking, so it is exercised where it applies.
    """
    origin = str(Path(__file__))
    own, caches = launch._the_hand_offs_own_files((origin,))
    assert origin in own
    assert importlib.util.cache_from_source(origin) in own
    # And named apart, because only a cache is matched by the name the
    # import system derives from it to write through.
    assert caches == (importlib.util.cache_from_source(origin),)


def test_a_source_with_no_cache_location_contributes_only_itself(monkeypatch) -> None:
    """An implementation that keeps no bytecode cache is answered, not tripped over.

    `cache_from_source` raises when `sys.implementation.cache_tag` is None,
    which is a real answer on an implementation that caches nothing rather than
    a failure — and this client runs where it is installed, not only on the
    interpreter it was written on.
    """

    def refuses(path: str) -> str:
        raise NotImplementedError("this implementation keeps no bytecode cache")

    monkeypatch.setattr(importlib.util, "cache_from_source", refuses)
    assert launch._the_hand_offs_own_files(("/nowhere/f.py",)) == (("/nowhere/f.py",), ())


def test_an_event_naming_a_hand_offs_bytecode_cache_is_not_the_programs() -> None:
    """The other half of the same rule, on the watch that reads it.

    The two clauses have two different lifetimes now, and this is where the
    difference is read: the name the import system DERIVES is the import
    system's whenever it appears, gate open or shut, while a cache's or a
    source's own name after the gate opened is something this proof cannot
    attribute — counted, not dropped.
    """
    origin = str(Path(__file__))
    cache = importlib.util.cache_from_source(origin)
    watch = harness.Watch()
    watch.arm((origin,), *launch._the_hand_offs_own_files((origin,)))
    watch.opening((compile("pass", origin, "exec"),))
    assert watch.judging
    # The name the import system derives from that cache to write through: it
    # appends a number of its own and renames, so only the derivation can match
    # it. Measured as the leak it closed: two of the hand-off's own file events
    # were judged as the program's in the cold package form.
    # After the gate opened a derived name is COUNTED, never judged: the
    # import system's act is not the program's, and a write this proof did
    # not see must not vanish behind a judged one.
    assert watch.whose((f"{cache}.1234567890", None)) == harness.NOT_JUDGED
    # The plain names, once the program has started.
    assert watch.whose((cache, "r")) == harness.NOT_JUDGED
    assert watch.whose((origin, "r")) == harness.NOT_JUDGED
    assert watch.whose(("something-else-entirely", "r")) == harness.THE_PROGRAMS


# --- A package's own `__init__` is the program's code ---------------------------


def a_package_whose_init_spawns(root: Path, init: Path, main: Path) -> Path:
    """A `-m` package that spawns from its `__init__` and again from its `__main__`."""
    tree = root / "pkg-init"
    inside = tree / "mypkg"
    inside.mkdir(parents=True)
    for module, marker in (("__init__.py", init), ("__main__.py", main)):
        (inside / module).write_text(
            f"import subprocess\n\nsubprocess.run(['touch', {str(marker)!r}], check=True)\n",
            encoding="utf-8",
        )
    return tree


def test_an_effect_a_packages_init_makes_is_judged_and_aborted(tmp_path: Path) -> None:
    """The `__init__` runs before the `__main__` and it is the program's own code.

    Measured as the defect: the launcher named only the `__main__` as the file
    whose execution starts the program, and the `__init__` runs earlier still —
    during the lookup that establishes the package HAS a `__main__` — so its
    effects were neither judged nor aborted. With an empty chain the run
    answered exit 6 for the `__main__`'s spawn while the `__init__`'s had
    already happened.
    """
    pack = plant_spawn_pack(tmp_path)
    init, main = tmp_path / "from-init", tmp_path / "from-main"
    tree = a_package_whose_init_spawns(tmp_path, init, main)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "-m",
            "mypkg",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=0" in stdout
    assert not init.exists(), "the `__init__`'s spawn was not judged, and happened"
    assert not main.exists()


def test_one_decision_does_not_govern_a_packages_init_and_its_main_both(tmp_path: Path) -> None:
    """The measured false all-clear through the package form, needing no thread.

    One record in the chain, two spawns. Before the `__init__` was watched this
    answered **exit 0 and `governed`** with both processes run — the same false
    all-clear a thread that outlives its main module produces, reached by a
    different road. The record now accounts for the `__init__`'s spawn, which
    really happened, and the `__main__`'s is refused.
    """
    pack = plant_spawn_pack(tmp_path)
    init, main = tmp_path / "from-init", tmp_path / "from-main"
    tree = a_package_whose_init_spawns(tmp_path, init, main)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN, count=1)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "-m",
            "mypkg",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert code != 0
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=1" in stdout
    assert init.exists(), "the decided spawn was refused"
    assert not main.exists(), "the undecided spawn happened"


def test_an_effect_a_parent_packages_init_makes_is_judged_too(tmp_path: Path) -> None:
    """`-m pkg.sub` runs `pkg`'s own `__init__` to find `sub`, and that is the program's.

    Resolving a dotted name one segment at a time is what reaches this: looking
    `pkg.sub` up in one step runs `pkg` before anything could have been told
    the program was starting, and the spawn then happened unjudged with the run
    reporting `not-exercised` — an absence over an effect.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "from-parent-init"
    tree = tmp_path / "parent"
    inside = tree / "pkg"
    inside.mkdir(parents=True)
    (inside / "__init__.py").write_text(
        f"import subprocess\n\nsubprocess.run(['touch', {str(marker)!r}], check=True)\n",
        encoding="utf-8",
    )
    (inside / "sub.py").write_text("pass\n", encoding="utf-8")
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "-m",
            "pkg.sub",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert code != exit_codes.EXIT_COULD_NOT_CHECK
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=0" in stdout
    assert not marker.exists(), "the parent package's spawn was not judged, and happened"


# --- The program's exit handlers are the program's ------------------------------


def a_tree_whose_exit_handler_spawns(
    root: Path, marker: Path, *, also_now: Path | None = None
) -> Path:
    """A program that registers a handler to run at exit, and maybe spawns first."""
    now = "" if also_now is None else f"subprocess.run(['touch', {str(also_now)!r}], check=True)\n"
    return a_quiet_tree(
        root,
        body=(
            "import atexit\n"
            "import subprocess\n"
            "\n"
            f"atexit.register(lambda: subprocess.run(['touch', {str(marker)!r}], check=True))\n"
            f"{now}"
        ),
    )


def test_an_effect_an_exit_handler_makes_is_judged_and_aborted(tmp_path: Path) -> None:
    """A handler the program registered is the program's own code, run under the watch.

    Measured as the defect: the disarm happened before the interpreter called
    the program's handlers, so the handler's spawn was neither judged nor
    aborted and the run answered `not-exercised` / exit 7 over an effect that
    happened.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "from-atexit"
    tree = a_tree_whose_exit_handler_spawns(tmp_path, marker)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert code != 0
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=0" in stdout
    assert not marker.exists(), "the exit handler's spawn was judged ungoverned and still happened"


def test_one_decision_does_not_govern_a_spawn_and_an_exit_handlers_too(tmp_path: Path) -> None:
    """One record, one spawn in the body and one at exit: the second is found.

    Before the exit handlers ran under the watch this answered **exit 0 and
    `governed`** with both processes run.
    """
    pack = plant_spawn_pack(tmp_path)
    decided, at_exit = tmp_path / "from-main", tmp_path / "from-atexit"
    tree = a_tree_whose_exit_handler_spawns(tmp_path, at_exit, also_now=decided)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN, count=1)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert code != 0
    assert f"ungoverned process-effects subprocess.Popen {SPAWN} events=1" in stdout
    assert decided.exists(), "the decided spawn was refused"
    assert not at_exit.exists(), "the undecided spawn happened"


def test_an_exit_handler_runs_once_and_the_report_survives_its_abort(tmp_path: Path) -> None:
    """The handler is stopped and the run still concludes, with one handler call.

    `atexit` reports what a handler raised and goes on, so the abort this
    harness raises into one does not stop the findings being written; and it
    clears its own register as it runs, so the interpreter's later call finds
    nothing and no handler runs twice.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "from-atexit"
    counted = tmp_path / "times-called"
    tree = a_quiet_tree(
        tmp_path,
        body=(
            "import atexit\n"
            "import subprocess\n"
            "\n"
            "\n"
            "def at_exit():\n"
            f"    with open({str(counted)!r}, 'a', encoding='utf-8') as opened:\n"
            "        opened.write('called\\n')\n"
            f"    subprocess.run(['touch', {str(marker)!r}], check=True)\n"
            "\n"
            "\n"
            "atexit.register(at_exit)\n"
        ),
    )
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert "inspected: process-effects" in stdout
    assert counted.read_text(encoding="utf-8") == "called\n"
    assert not marker.exists()


# --- A gate that never opened concludes nothing ---------------------------------


def a_sourceless_module(root: Path, marker: Path) -> Path:
    """A `-m` target the interpreter runs from bytecode with no source beside it.

    The code object then carries the file it was compiled FROM, which is gone,
    so nothing the launcher resolved matches it and the gate stays shut. It is
    the one shape of target this mechanism cannot watch, and the point of the
    test is that the run says so.
    """
    tree = root / "sourceless"
    tree.mkdir()
    source = tree / "solo.py"
    source.write_text(
        f"import subprocess\n\nsubprocess.run(['touch', {str(marker)!r}], check=True)\n",
        encoding="utf-8",
    )
    py_compile.compile(str(source), cfile=str(tree / "solo.pyc"), doraise=True)
    source.unlink()
    return tree


@pytest.mark.parametrize("as_json", [False, True])
def test_a_gate_that_never_opened_says_so_and_reports_no_verdict(
    tmp_path: Path, as_json: bool
) -> None:
    """Exit 7 with the sentence, never `not-exercised`: nothing was watched.

    Measured as the defect: this run printed
    `not-exercised … events=0` — byte for byte what a program that never walked
    the path produces — while the spawn happened. « This run established an
    absence » and « this run never began watching » are different facts, and
    the rest of this harness is fastidious about exactly that distinction: the
    sentence and the problem code say which one happened, and no verdict line is
    printed at all.

    The status is 7, the local check that could not conclude — the plane was
    asked, its chain was read, and what could not be done was the watching. It
    was 4 for a while, which a shell reads as « the control plane could not be
    asked » about a control plane that had answered.

    The spawn happening is asserted, not excused: it is why the run must report
    no verdict at all.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "from-sourceless"
    tree = a_sourceless_module(tmp_path, marker)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            *(["--json"] if as_json else []),
            "--",
            "-m",
            "solo",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert code != exit_codes.EXIT_COULD_NOT_ASK
    assert "not-exercised" not in stdout + stderr
    # The harness says it on its own stream whichever rendering was asked for.
    assert "never saw the program's own code start" in stderr
    assert marker.exists(), "the program did not run, so this proves nothing about the gate"
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["problem"]["code"] == "answer_unreadable"
        assert "never saw the program's own code start" in envelope["problem"]["message"]
    else:
        assert stdout == ""


def test_the_watch_remembers_that_it_once_started(tmp_path: Path) -> None:
    """`disarm` clears `started`, and the run still has to know it ever did.

    Without a fact that outlives the disarm, « the gate never opened » is
    unaskable after the program is done — and the harness answers it after the
    program is done.
    """
    watch = harness.Watch()
    assert not watch.ever_started
    watch.arm((__file__,), (__file__,), ())
    watch.opening((compile("pass", __file__, "exec"),))
    assert watch.judging
    watch.disarm()
    assert not watch.judging
    assert watch.ever_started


def a_tree_whose_module_writes_beside_its_own_cache(root: Path) -> Path:
    """A `-m` program that reads a file beside it, then writes to a name derived
    from its own bytecode cache — the one shape the hand-off's exclusion still
    reaches after the program started, because a cache path is the import
    system's to derive and not the launcher's to know in advance."""
    tree = root / "own-cache"
    tree.mkdir()
    (tree / "beside.txt").write_text("read me\n", encoding="utf-8")
    (tree / "mod_app.py").write_text(
        "import importlib.util\n"
        "with open('beside.txt', encoding='utf-8') as opened:\n"
        "    opened.read()\n"
        "derived = importlib.util.cache_from_source(__file__) + '.9999'\n"
        "import os\n"
        "os.makedirs(os.path.dirname(derived), exist_ok=True)\n"
        "with open(derived, 'w', encoding='utf-8') as mine:\n"
        "    mine.write('not a cache')\n",
        encoding="utf-8",
    )
    return tree


def test_a_write_beside_the_programs_own_cache_is_counted_and_never_a_pass(
    tmp_path: Path,
) -> None:
    """The derived-cache clause is not judged and not aborted — a cache is the
    import system's act — but once the gate is open it is COUNTED, so a run
    cannot read `governed` over a write this proof did not see. Measured before
    this rule: exit 0, `governed`, no count, the write never mentioned."""
    pack = a_pack_watching_the_interpreters_own_reads(tmp_path)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(READING, count=1)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "-m",
            "mod_app",
            cwd=a_tree_whose_module_writes_beside_its_own_cache(tmp_path),
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK, (stdout, stderr)
    assert f"governed watcher builtins.open {READING} events=1" in stdout
    assert f"unjudged: 1 watcher builtins.open {READING}" in stdout
    assert "target exit: 0" in stdout


# --- The code and the sentence are never the target's to choose -----------------


@pytest.mark.parametrize("status", [7, 64])
def test_the_code_a_shell_reads_is_never_chosen_by_the_targets_own_number(
    tmp_path: Path, status: int
) -> None:
    """One event, one reading, whatever number the program leaves by.

    The program runs inside the harness's own interpreter, so `os._exit(64)`
    ends that process with 64 — and 64 was read here as « the verification was
    refused before it began, and the harness said why on this stream », while
    the harness had said nothing and the program had run. `os._exit(7)` produced
    the correct 4. One event reading two ways because of the target's own number
    is the collision `exit_codes.py` exists to prevent, so both are asserted
    together: the answer is the same, and it is the honest one.
    """
    pack = plant_spawn_pack(tmp_path)
    tree = a_quiet_tree(tmp_path, body=f"import os\n\nos._exit({status})\n")
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_COULD_NOT_ASK, (stdout, stderr)
    assert code != exit_codes.EXIT_MISUSE
    assert "refused before it began" not in stderr
    assert "did not run to a conclusion" in stderr


def verify_json(*argv: str, cwd: Path) -> dict:
    """One run under `--json`, with the envelope read off stdout and nothing else.

    `--json` is inserted before the separator, never appended: after it the word
    is one of the PROGRAM's arguments, and a helper that handed the flag to the
    target would test the prose rendering while claiming to test the envelope.
    """
    at = list(argv).index(harness.SEPARATOR)
    code, stdout, stderr = verify(*argv[:at], "--json", *argv[at:], cwd=cwd)
    assert code != 0, (stdout, stderr)
    return json.loads(stdout)


def test_an_unreadable_chain_and_a_gate_that_never_opened_are_distinct_problems(
    tmp_path: Path,
) -> None:
    """Two facts, one problem document: the cause survived only as prose on stderr.

    « The chain could not be read while the program ran » and « the verifier
    never saw the program's own code start » are different facts about different
    things, and both rendered as `answer_unreadable` carrying the one sentence
    about a verification that did not conclude. A machine reading the envelope
    could not tell them apart at all. The harness's own account of how it ended
    carries which, and each answers with its own code and its own sentence.

    The chain half's code is the TRANSPORT's, carried through the harness's
    outcome file and not minted here: a page in a generation this client does
    not speak is `generation_unsupported`, which is what the transport
    classified it as — a daemon that was reached and answered. This client
    publishing `unreachable` for it would be deriving a classification nobody
    gave it (article 1), and the sentence beside it would have said « the
    connection was opened on contract version … » under a code meaning the far
    end could not be reached.
    """
    pack = plant_spawn_pack(tmp_path)
    marker = tmp_path / "from-sourceless"
    stopping = {"/scopes/": (200, [no_evidence_page(), foreign_generation_page()])}
    with answering_by_path(tmp_path / "stopping.sock", stopping) as address:
        unreadable = verify_json(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=a_spawning_tree(tmp_path),
        )
    with answering_by_path(
        tmp_path / "serving.sock", {"/scopes/": (200, no_evidence_page())}
    ) as address:
        shut = verify_json(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "-m",
            "solo",
            cwd=a_sourceless_module(tmp_path, marker),
        )
    assert unreadable["problem"]["message"] != shut["problem"]["message"]
    assert "chain" in unreadable["problem"]["message"]
    assert "never saw the program's own code start" in shut["problem"]["message"]
    assert unreadable["problem"]["code"] == "generation_unsupported"
    assert shut["problem"]["code"] == "answer_unreadable"
    assert unreadable["problem"]["code"] != shut["problem"]["code"]


def test_the_no_answer_envelope_does_not_share_a_stream_with_the_program(tmp_path: Path) -> None:
    """A program can print a fake problem object; the tests parse from the first `{`.

    The program's two streams go to this command's error stream by design — the
    answer to `verify` is the report — so the first `{` a machine reader finds
    there can be the PROGRAM's. The envelope goes to stdout on the no-answer
    paths, where nothing else is written since there is no report to render, and
    the rule is stated in the module.
    """
    pack = plant_spawn_pack(tmp_path)
    tree = a_quiet_tree(
        tmp_path,
        body=(
            "import subprocess\n\n"
            'print(\'{"problem": {"code": "forged", "message": "all clear"}}\')\n'
            "subprocess.run(['true'], check=True)\n"
        ),
    )
    routes = {"/scopes/": (200, [no_evidence_page(), foreign_generation_page()])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--json",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_COULD_NOT_ASK, (stdout, stderr)
    # The transport's own code for the reply the chain gave, carried through the
    # harness's outcome file — and, for this test, evidence that the envelope on
    # stdout is the real one rather than the program's.
    assert json.loads(stdout)["problem"]["code"] == "generation_unsupported"
    assert "forged" in stderr, "the program's own output no longer reaches the error stream"
    assert "forged" not in stdout


def test_a_pack_naming_an_absent_attribute_on_a_later_import_is_refused_here_too(
    tmp_path: Path,
) -> None:
    """The verifier hands the program over through the same launcher, so it meets
    the same refusal from inside the program's own import — and answers it the
    way `instrument run` answers it, 64, off the harness's own account of how it
    ended rather than off the number the process happened to exit with."""
    pack = plant_pack(
        tmp_path,
        name="absent-on-import",
        module="sqlite3",
        attribute="nosuchattr",
        capability="database.open",
        interpose=FIRST_ARGUMENT_INTERPOSE,
    )
    tree = a_quiet_tree(tmp_path, body="import sqlite3\n\nprint(sqlite3.sqlite_version)\n")
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, no_evidence_page())}) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == exit_codes.EXIT_MISUSE, (stdout, stderr)
    assert code != exit_codes.EXIT_DENY
    assert "has no nosuchattr" in stderr
    assert "Traceback" not in stderr
    assert "governed" not in stdout


# --- The window the launcher declares its own, measured rather than guarded -----

#: A package named to `-m` by a dotted name, and the module named after it. The
#: package's own body opens the gate — an `__init__` is the program's code — and
#: installs a finder of its own, so that code the PROGRAM wrote runs at the one
#: moment the launcher is between what it knows: after the `__init__` and before
#: the module. Nothing here sleeps, spawns or races.
_A_PACKAGE_THAT_WATCHES_ITS_OWN_LOOKUP = """\
import sys

import window_probe

window_probe.executing()
window_probe.look("the __init__ body")


class Asked:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.endswith(".sub"):
            window_probe.look("code of the program's own, during a lookup")
        return None


sys.meta_path.insert(0, Asked())
"""

_THE_MODULE_NAMED_AFTER_IT = """\
import window_probe

window_probe.executing()
window_probe.look("the module's body")
"""


def test_the_between_segments_window_is_measured_and_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`launch.py` names a stretch it declares its own; this is that stretch, measured.

    Resolving `-m pkg.sub` runs `pkg`'s `__init__` — the program's own code,
    which opens the gate — and the launcher must then tell the watch again what
    it has learned, because the file of the module it is about to look up is not
    yet in the set it excludes. Telling it shuts the gate, and everything until
    the module's own body executes is attributed to the hand-off: not judged,
    not counted, not aborted.

    Driven in process and without an audit hook, because a hook can never be
    taken out of an interpreter again. The one event the gate keys on — the
    interpreter reporting one of the program's own code objects — is supplied
    from the module bodies themselves, which is the same code object the
    interpreter would have handed a hook.

    Deterministic by construction: the package installs a finder of its own, so
    code the program wrote runs inside the launcher's next lookup rather than
    racing it from a thread. What is asserted is the shape of the window, which
    is machine-independent; its width is not, and is recorded in `launch.py`
    beside the statement it replaces.
    """
    package = tmp_path / "wpkg"
    package.mkdir()
    (package / "__init__.py").write_text(_A_PACKAGE_THAT_WATCHES_ITS_OWN_LOOKUP, encoding="utf-8")
    (package / "sub.py").write_text(_THE_MODULE_NAMED_AFTER_IT, encoding="utf-8")

    watch = harness.Watch()
    seen: list[tuple[str, bool]] = []
    probe = importlib.util.module_from_spec(
        importlib.util.spec_from_loader("window_probe", loader=None)
    )
    # `executing` is the interpreter's own report of a code object, and nothing
    # else; `look` asks the watch the only question this test is about.
    probe.executing = lambda: watch.opening((sys._getframe(1).f_code,))  # type: ignore[attr-defined]
    probe.look = lambda where: seen.append((where, watch.judging))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "window_probe", probe)

    armed: list[bool] = []

    def starting(starts: tuple[str, ...], own: tuple[str, ...], caches: tuple[str, ...]) -> None:
        watch.arm(starts, own, caches)
        armed.append(watch.judging)

    monkeypatch.chdir(tmp_path)
    try:
        launch.hand_over(["-m", "wpkg.sub"], err=io.StringIO(), starting=starting)
    finally:
        sys.meta_path[:] = [found for found in sys.meta_path if type(found).__name__ != "Asked"]
        for name in [name for name in sys.modules if name.split(".")[0] == "wpkg"]:
            del sys.modules[name]

    # Two arms, and each of them shuts the gate: that is what makes a window.
    assert armed == [False, False], armed
    # The `__init__` body opened it, the module's body opened it again, and in
    # between the program's own code ran with the gate shut. The stretch is
    # entered once per remaining segment, which is why this is a window and not
    # a hole: nothing outside it is affected.
    assert seen == [
        ("the __init__ body", True),
        ("code of the program's own, during a lookup", True),
        ("code of the program's own, during a lookup", False),
        ("the module's body", True),
    ], seen
    assert watch.ever_started


# --- the outcome file's code is the transport's, and an unknown is not promoted ---


def _said(tmp_path: Path, **members: object) -> Path:
    """One outcome file, written as the harness writes it."""
    outcome = tmp_path / verify_command.OUTCOME_FILE
    outcome.write_text(json.dumps(members), encoding="utf-8")
    return outcome


def _answered(outcome: Path) -> tuple[int, dict]:
    """What `verify` answers for that outcome file, as the code and the envelope."""
    arguments = argparse.Namespace(json=True)
    out, err = io.StringIO(), io.StringIO()
    code = verify_command._no_answer(outcome, arguments, out, err)
    return code, json.loads(out.getvalue())


def test_a_code_the_registry_carries_is_the_one_the_envelope_publishes(tmp_path: Path) -> None:
    """Anti-vacuity for the test below: a known code really is promoted.

    Read straight off the reading rule rather than through a run, because the
    two halves differ only in the one member and no daemon can be made to
    produce both on demand.
    """
    code, envelope = _answered(
        _said(
            tmp_path,
            outcome=harness.CHAIN_UNREADABLE_DURING,
            detail="the daemon said so",
            problem_code="evidence_store_unavailable",
        )
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert envelope["problem"]["code"] == "evidence_store_unavailable"
    assert "the daemon said so" in envelope["problem"]["message"]


def test_a_code_the_registry_does_not_know_is_not_promoted(tmp_path: Path) -> None:
    """An unknown is never read as more precise than the fallback (article 3).

    A code this client cannot ask the registry about — for its retryability, for
    its class — is one it must not publish as the classification of anything, so
    the envelope answers the fallback and the harness's own sentence survives.
    """
    code, envelope = _answered(
        _said(
            tmp_path,
            outcome=harness.CHAIN_UNREADABLE_DURING,
            detail="a word from a later generation",
            problem_code="chain_went_sideways",
        )
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert envelope["problem"]["code"] == verify_command.UNCLASSIFIED.value
    assert envelope["problem"]["code"] != "chain_went_sideways"
    assert "the chain could not be read while the program ran" in envelope["problem"]["message"]


def test_findings_that_exist_and_will_not_read_answer_the_code_for_a_check(
    tmp_path: Path,
) -> None:
    """`reported` with no report this client can read is 7, not 4.

    With the outcome file the client KNOWS the findings exist, which is what 7
    is for — and it is the code `_unreadable` answers for the identical sentence
    and the one `docs/PACKS.md` states. It was 4, which said the verification
    could not be obtained about a run that had concluded and written it down.
    """
    code, envelope = _answered(_said(tmp_path, outcome=harness.REPORTED, detail=""))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert code != exit_codes.EXIT_COULD_NOT_ASK
    assert envelope["problem"]["message"] == verify_command.UNREADABLE_FINDINGS
    # And no path inside a directory this command has already removed.
    assert "sayfirst-verify-" not in envelope["problem"]["message"]


# --- a read the control plane refused is refused, not « could not ask » --------


def test_a_chain_read_the_plane_refused_answers_refused(tmp_path: Path) -> None:
    """3 and not 4: the plane was asked, and it said no.

    Every other command of this client answers a refused read with 3. `verify`
    answered 4 for it — « the control plane could not be asked » — about a
    control plane that had been asked and had answered.
    """
    code, envelope = _answered(
        _said(
            tmp_path,
            outcome=harness.CHAIN_UNREADABLE_BEFORE,
            detail="the scope is not one the daemon reads",
            problem_code="scope_invalid",
            problem_class="refused",
        )
    )
    assert code == exit_codes.EXIT_REFUSED
    assert envelope["problem"]["code"] == "scope_invalid"


def test_the_class_the_harness_carried_decides_and_not_the_registry(tmp_path: Path) -> None:
    """A problem this client minted is « could not ask », whatever class its code has.

    The transport mints `generation_unsupported`, which the registry classes as
    refused, for an answer in a generation this client does not read: nobody
    refused anything. The class travels in the outcome file for that reason.
    """
    code, envelope = _answered(
        _said(
            tmp_path,
            outcome=harness.CHAIN_UNREADABLE_DURING,
            detail="an answer in another generation",
            problem_code="generation_unsupported",
            problem_class="could_not_ask",
        )
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert envelope["problem"]["code"] == "generation_unsupported"


@pytest.mark.parametrize("carried", [None, "declined", 3])
def test_a_class_this_command_cannot_read_is_not_read_as_refused(
    tmp_path: Path, carried: object
) -> None:
    """An absent or unknown class is the fallback, never the more precise answer."""
    members: dict[str, object] = {
        "outcome": harness.CHAIN_UNREADABLE_BEFORE,
        "detail": "",
        "problem_code": "scope_invalid",
    }
    if carried is not None:
        members["problem_class"] = carried
    code, _ = _answered(_said(tmp_path, **members))
    assert code == exit_codes.EXIT_COULD_NOT_ASK


def test_a_refused_class_on_an_ending_that_carries_no_read_changes_nothing(
    tmp_path: Path,
) -> None:
    """Only a chain read is classified; the harness's own endings keep their codes."""
    code, _ = _answered(
        _said(tmp_path, outcome=harness.REPORTED, detail="", problem_class="refused")
    )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK


def test_a_refused_class_with_a_code_the_registry_does_not_know_is_not_refused(
    tmp_path: Path,
) -> None:
    """The fallback code is a « could not ask » code, and the status goes with it."""
    code, envelope = _answered(
        _said(
            tmp_path,
            outcome=harness.CHAIN_UNREADABLE_BEFORE,
            detail="",
            problem_code="chain_went_sideways",
            problem_class="refused",
        )
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert envelope["problem"]["code"] == verify_command.UNCLASSIFIED.value


@pytest.mark.parametrize(
    ("answered", "expected"),
    [(True, "refused"), (False, "could_not_ask")],
)
def test_the_harness_writes_the_class_of_the_problem_it_carries(
    tmp_path: Path, answered: bool, expected: str
) -> None:
    """Asked of the value: the same code is refused when the plane sent it and
    « could not ask » when this client minted it for an answer it could not read."""
    from sayfirst_contract.problems import Problem, ProblemCode

    outcome = tmp_path / "outcome.json"
    problem = Problem(
        ProblemCode.GENERATION_UNSUPPORTED,
        "another generation",
        False,
        1,
        control_plane_answered=answered,
    )
    harness._write_outcome(outcome, harness.CHAIN_UNREADABLE_BEFORE, "d", problem=problem)
    written = json.loads(outcome.read_text(encoding="utf-8"))
    assert written["problem_code"] == "generation_unsupported"
    assert written["problem_class"] == expected


def _verify_against(tmp_path: Path, pages: object) -> tuple[int, str, str]:
    pack = plant_spawn_pack(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, pages)}) as address:
        return verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--json",
            "--",
            "app.py",
            cwd=tree,
        )


def test_verify_answers_refused_when_the_plane_refuses_the_first_read(tmp_path: Path) -> None:
    code, stdout, stderr = _verify_against(tmp_path, [(403, problem("scope_refused"))])
    assert code == exit_codes.EXIT_REFUSED, (stdout, stderr)
    assert json.loads(stdout)["problem"]["code"] == "scope_refused"


def test_verify_answers_refused_when_the_plane_refuses_a_read_while_the_program_runs(
    tmp_path: Path,
) -> None:
    code, stdout, stderr = _verify_against(
        tmp_path, [no_evidence_page(), (403, problem("principal_refused"))]
    )
    assert code == exit_codes.EXIT_REFUSED, (stdout, stderr)
    assert json.loads(stdout)["problem"]["code"] == "principal_refused"
    assert "while the program ran" in json.loads(stdout)["problem"]["message"]


def test_verify_still_answers_could_not_ask_when_the_plane_cannot_answer(tmp_path: Path) -> None:
    """The other class, through the same path: a store that is down is not a refusal."""
    code, stdout, stderr = _verify_against(
        tmp_path, [no_evidence_page(), (503, problem("evidence_store_unavailable"))]
    )
    assert code == exit_codes.EXIT_COULD_NOT_ASK, (stdout, stderr)
    assert json.loads(stdout)["problem"]["code"] == "evidence_store_unavailable"


# --- the program's diagnostics are not the report, and cannot discard it --------

#: A program that prints a byte no locale decodes, on both of its streams, and
#: then walks the governed path and ends normally. The byte is written to the
#: descriptor rather than through `print`, because a text stream would refuse
#: it here rather than in the parent — and the parent is where the defect was.
A_PROGRAM_THAT_PRINTS_A_BYTE = """\
import os
import subprocess

os.write(1, b"\\xff")
os.write(2, b"\\xfe")
subprocess.run(["true"], check=True)
"""


def test_a_byte_the_program_printed_never_discards_a_completed_verification(
    tmp_path: Path,
) -> None:
    """A target's diagnostics are decoded leniently; its verdict still arrives.

    Measured as the defect: the harness's two streams were captured with
    strict locale decoding, so one byte of `0xff` from an arbitrary Python
    program raised `UnicodeDecodeError` in the PARENT, before the report file
    was read. A verification that had run to a conclusion — one spawn, one
    recorded allow, `governed` written down — was thrown away by output that
    said nothing about governance at all.

    The report does not travel on either of these streams: the harness writes
    it to a file of its own (`harness._write_report`) and this command reads
    that file, strictly, in `_findings`. So leniency here reaches diagnostics
    only, and the test below holds the report's own channel to the opposite
    rule.
    """
    pack = plant_spawn_pack(tmp_path)
    tree = a_quiet_tree(tmp_path, body=A_PROGRAM_THAT_PRINTS_A_BYTE)
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page(SPAWN)])}
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = verify(
            "--pack",
            str(pack),
            "--socket",
            str(address),
            "--scope",
            "local",
            "--ungoverned",
            "--",
            "app.py",
            cwd=tree,
        )
    assert code == 0, (stdout, stderr)
    assert f"governed process-effects subprocess.Popen {SPAWN} events=1" in stdout
    assert "target exit: 0" in stdout
    assert "UnicodeDecodeError" not in stderr
    # The bytes were not dropped either: both streams reached the diagnostic
    # stream, each byte standing as the replacement character.
    assert stderr.count("�") >= 2, stderr


def test_a_report_this_client_cannot_decode_is_an_inability_and_never_a_verdict(
    tmp_path: Path,
) -> None:
    """The report's own channel stays strict: a mangled report is no verdict.

    The twin of the test above, and the reason the leniency there is confined
    to `_harness`. Replacement-decoding the findings would turn bytes nobody
    wrote as a report into a document that might parse — a quietly wrong
    verdict, which is worse than the crash being removed. `_findings` answers
    « there are no findings », which `run` reports as a verification that
    concluded nothing.
    """
    report = tmp_path / verify_command.REPORT_FILE
    report.write_bytes(b'{"points": [{"verdict": "governed\xff"}]}\n')
    assert verify_command._findings(report) is None


def test_a_run_matches_records_by_its_correlation_not_by_a_connection() -> None:
    """The fix for a multi-effect governed run: records span connections, one token.

    The shipped boundary holds one connection per grant, so a run that asks about
    two kinds of effect writes two records on two connections. Both are this
    run's, and the token this run stamped is what says so — the first record as
    much as the second.
    """
    chain = harness.Chain(
        connection=None,  # type: ignore[arg-type]
        scope="local",
        floor=0,
        one_execution=True,
        correlation="sayfirst-verify:the-run",
    )
    mine_first = {"correlation": "sayfirst-verify:the-run", "connection_id": "c-1"}
    mine_second = {"correlation": "sayfirst-verify:the-run", "connection_id": "c-2"}
    another = {"correlation": "sayfirst-verify:another-run", "connection_id": "c-3"}
    absent = {"connection_id": "c-4"}
    # Both of this run's records match, though they name different connections;
    # the first is held to the token, not trusted for naming it.
    assert harness._this_runs_correlation(chain, mine_first) is True
    assert harness._this_runs_correlation(chain, mine_second) is True
    # Another execution's token, and a record carrying none, are not this run's.
    assert harness._this_runs_correlation(chain, another) is False
    assert harness._this_runs_correlation(chain, absent) is False


def test_an_ungoverned_run_requires_no_correlation() -> None:
    """`--ungoverned` stamped nothing, so the chain alone answers and every record
    is another execution's by construction."""
    chain = harness.Chain(
        connection=None,  # type: ignore[arg-type]
        scope="local",
        floor=0,
        one_execution=False,
        correlation=None,
    )
    assert harness._this_runs_correlation(chain, {"correlation": None}) is True
