# SPDX-License-Identifier: Apache-2.0
"""An offline audit renders the contract's verdict for every published manifest vector."""

from __future__ import annotations

import io
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from sayfirst_contract.artifacts import load_json
from sayfirst_contract.evidence import ChainCondition, Rederivation, verify_export

from sayfirst_cli import exit_codes
from sayfirst_cli.main import main

VECTORS = load_json("domain", "evidence-export-manifest-vectors.json")["vectors"]
BY_NAME = {vector["name"]: vector["bundle"] for vector in VECTORS}


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(["evidence", "audit", *argv], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture(autouse=True)
def every_audit_here_is_offline(no_socket):
    """Not one test in this file may open a socket; the guard is `conftest.py`'s."""


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["name"])
def test_offline_audit_matches_the_published_verifier(tmp_path: Path, vector):
    bundle = vector["bundle"]
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code, stdout, stderr = run("--file", str(path), "--json")

    from sayfirst_cli.evidence import exit_for

    verdict = verify_export(bundle)
    envelope = json.loads(stdout)
    assert envelope["result"] == {
        "served": bundle["verification"],
        "local_check": verdict.to_document(),
    }
    assert envelope["verification"] == {"server_uid": None, "expected": None, "verified": False}
    assert code == exit_for(verdict)
    assert stderr == ""


@pytest.mark.parametrize(
    ("name", "condition", "expected"),
    [
        ("v1_intact_range", ChainCondition.intact, exit_codes.EXIT_COULD_NOT_CHECK),
        ("v2_broken_chain", ChainCondition.broken_at, exit_codes.EXIT_COULD_NOT_CHECK),
        (
            "v2_unknown_preimage_version",
            ChainCondition.unverifiable,
            exit_codes.EXIT_COULD_NOT_CHECK,
        ),
    ],
)
def test_named_vector_exit_codes_follow_the_actual_contract(name, condition, expected):
    """The verifier is the authority on the verdict, and this client renders it.

    Three published bundles, read rather than assumed: all three rederive
    nothing, so the overall verdict is `unverifiable` and the exit is 7 for each
    — including the one whose chain the verifier found broken, because a
    rederivation that could not be attempted takes precedence over a chain
    finding in `exit_for`.

    The two chain conditions are the pair worth keeping apart, and this row is
    where they are held apart. `broken_at` is a negative fact the verifier
    ESTABLISHED: it recomputed a hash and the number did not match.
    `unverifiable` is the absence of one — it holds no reader for the recipe an
    entry declares, so it established nothing and says so. The unknown-recipe
    bundle is the second, and rendering it as damage would be an absence
    published as a finding (article 2).
    """
    from sayfirst_cli.evidence import exit_for

    verdict = verify_export(BY_NAME[name])
    assert verdict.chain.condition is condition
    assert verdict.manifest_hash_recomputes is True
    assert verdict.overall is Rederivation.unverifiable
    assert exit_for(verdict) == expected


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (ChainCondition.intact, 0),
        (ChainCondition.broken_at, exit_codes.EXIT_CHECK_FAILED),
        (ChainCondition.gap_at, exit_codes.EXIT_CHECK_FAILED),
        (ChainCondition.unverifiable, exit_codes.EXIT_COULD_NOT_CHECK),
    ],
)
def test_chain_exit_codes(condition, expected):
    from sayfirst_cli.evidence import exit_for

    chain = verify_export(BY_NAME["v1_intact_range"]).chain
    assert exit_for(replace(chain, condition=condition)) == expected


#: A member neither vocabulary defines today. Invented rather than borrowed from
#: a later generation, because the point is precisely that this client has never
#: heard of it — an actual future member would be a name somebody could look up.
UNKNOWN_TO_THIS_GENERATION = "a-word-this-generation-does-not-define"


@pytest.mark.parametrize("member", ["condition", "overall"])
def test_a_verdict_member_this_client_does_not_know_is_could_not_check(member):
    """A generation that adds a member is a check this client cannot perform.

    Measured before the fallback: a subscript, so a member outside either
    vocabulary left `evidence audit` in a `KeyError` — and a traceback ends the
    process with exit 1, which this client publishes as « the control plane
    answered deny ». An unknown verdict is not a denial and not a finding; it is
    a check that could not conclude, and 7 is what that is for.

    Both vocabularies are driven, because they are read by two different
    branches of the same function and a fallback on one proves nothing about the
    other.
    """
    from sayfirst_cli.evidence import exit_for

    verdict = verify_export(BY_NAME["v1_intact_range"])
    if member == "condition":
        subject = replace(verdict.chain, condition=UNKNOWN_TO_THIS_GENERATION)
    else:
        subject = replace(verdict, overall=UNKNOWN_TO_THIS_GENERATION)
    assert exit_for(subject) == exit_codes.EXIT_COULD_NOT_CHECK
    assert exit_for(subject) != exit_codes.EXIT_DENY


def test_a_member_this_generation_does_define_never_takes_the_fallback():
    """Anti-vacuity: a fallback that swallowed the known members would pass above.

    Every chain condition is put through the same function and required to
    answer something the table states, so the clause added for the unknown
    cannot quietly become the answer for everything; the rederivation members
    are held the same way by the parametrised case below.
    """
    from sayfirst_cli.evidence import exit_for

    chain = verify_export(BY_NAME["v1_intact_range"]).chain
    assert exit_for(replace(chain, condition=ChainCondition.intact)) == 0
    assert (
        exit_for(replace(chain, condition=ChainCondition.broken_at)) == exit_codes.EXIT_CHECK_FAILED
    )
    assert {exit_for(replace(chain, condition=condition)) for condition in ChainCondition} == {
        0,
        exit_codes.EXIT_CHECK_FAILED,
        exit_codes.EXIT_COULD_NOT_CHECK,
    }


@pytest.mark.parametrize(
    ("overall", "recomputes", "condition", "expected"),
    [
        (Rederivation.confirmed, True, ChainCondition.intact, 0),
        (Rederivation.differs, True, ChainCondition.intact, exit_codes.EXIT_CHECK_FAILED),
        (Rederivation.confirmed, False, ChainCondition.intact, exit_codes.EXIT_CHECK_FAILED),
        (Rederivation.confirmed, True, ChainCondition.broken_at, exit_codes.EXIT_CHECK_FAILED),
        (Rederivation.confirmed, True, ChainCondition.gap_at, exit_codes.EXIT_CHECK_FAILED),
        (Rederivation.unverifiable, True, ChainCondition.intact, exit_codes.EXIT_COULD_NOT_CHECK),
        (
            Rederivation.unverifiable,
            False,
            ChainCondition.broken_at,
            exit_codes.EXIT_COULD_NOT_CHECK,
        ),
        (Rederivation.differs, None, ChainCondition.broken_at, exit_codes.EXIT_COULD_NOT_CHECK),
    ],
)
def test_export_exit_precedence(overall, recomputes, condition, expected):
    from sayfirst_cli.evidence import exit_for

    verdict = verify_export(BY_NAME["v1_intact_range"])
    verdict = replace(
        verdict,
        overall=overall,
        manifest_hash_recomputes=recomputes,
        chain=replace(verdict.chain, condition=condition),
    )
    assert exit_for(verdict) == expected


@pytest.mark.parametrize("extra", [("--socket", "d.sock"), ("--scope", "local")])
def test_file_excludes_online_connection_arguments(extra):
    with pytest.raises(SystemExit) as failure:
        run("--file", "bundle.json", *extra)
    assert failure.value.code == 2


@pytest.mark.parametrize("bundle", [{"unrelated": True}, [], {"scope": "local"}])
@pytest.mark.parametrize("as_json", [False, True])
def test_a_non_bundle_reports_the_contracts_structural_issues(tmp_path: Path, bundle, as_json):
    path = tmp_path / "not-a-bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code, stdout, stderr = run("--file", str(path), *(["--json"] if as_json else []))
    verdict = verify_export(bundle)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    if as_json:
        assert json.loads(stdout)["result"] == {
            "served": None,
            "local_check": verdict.to_document(),
        }
    else:
        assert stdout.startswith("local_check: unverifiable\n")
        for issue in verdict.issues:
            assert f"issue: {issue}\n" in stdout
        assert "verification: not stated\n" in stdout
    assert stderr == ""


@pytest.mark.parametrize("manifest", ["recomputes", "mismatch", "unknown"])
def test_offline_prose_keeps_local_and_served_verdicts_separate(tmp_path: Path, manifest):
    bundle = dict(BY_NAME["v1_intact_range"])
    expected = "recomputes"
    if manifest == "mismatch":
        bundle["manifest_hash"] = "0" * 64
        expected = "does not recompute"
    elif manifest == "unknown":
        bundle["manifest_version"] = "sayfirst-control-plane/evidence-export/v9"
        expected = "unknown version sayfirst-control-plane/evidence-export/v9"
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code, stdout, stderr = run("--file", str(path))
    verdict = verify_export(bundle)
    assert stdout.splitlines() == [
        f"local_check: {verdict.overall}",
        f"manifest: {expected}",
        f"chain: {verdict.chain.condition}",
        f"coverage: {verdict.coverage}",
        *(f"issue: {issue}" for issue in verdict.issues),
        "verification: intact",
    ]
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stderr == ""


@pytest.mark.parametrize("contents", [None, "{not json", "\udcff"])
def test_unreadable_file_is_could_not_check(tmp_path: Path, contents):
    path = tmp_path / "bad.json"
    if contents is not None:
        path.write_bytes(contents.encode("utf-8", errors="surrogateescape"))
    code, stdout, stderr = run("--file", str(path))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stdout == ""
    assert "could not check:" in stderr


#: The shapes of bundle content this verifier cannot judge, and what each one
#: stops it judging. Every one of them is a document a JSON parser produces and
#: an ordinary mistake makes — a range assembled out of order, a page of the
#: wrong scope, a grade entry with no members, a delegation that is not a chain,
#: an instant at the edge of the calendar.
UNJUDGEABLE = {
    "order": (lambda b: b["entries"].insert(0, b["entries"].pop(1)), ChainCondition.unverifiable),
    "scope": (
        lambda b: b["entries"][1].__setitem__("scope", "another"),
        ChainCondition.unverifiable,
    ),
    "asserted_grade": (
        lambda b: b["verification"].__setitem__("grades", [{}]),
        ChainCondition.intact,
    ),
    "principal": (
        lambda b: b["entries"][0]["principal"].__setitem__("via", [None]),
        ChainCondition.unverifiable,
    ),
    "instant": (
        lambda b: b["entries"][0].__setitem__("recorded_at", "0001-01-01T00:00:00+01:00"),
        ChainCondition.unverifiable,
    ),
}


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("damage", sorted(UNJUDGEABLE))
def test_content_the_verifier_cannot_judge_is_a_verdict_and_never_an_exception(
    tmp_path: Path, as_json, damage
):
    """A bundle's content is a verdict, whatever is wrong with it — exit 7, not 4.

    Each of these inputs used to come out of the verifier as an exception, which
    this client caught and rendered as « could not check » with the exception's
    own sentence: a 7 that said nothing about WHERE the range stopped being
    checkable. The verifier is total over documents a parser produces now, so
    each is an `unverifiable` verdict instead, and this client renders it as one
    — on stdout, as the answer it is, with the sequence and the recipe beside it.

    The exit is the same 7 either way, and that is the point: « the answer was
    obtained and the check could not conclude » was always the honest reading,
    and it is now said with the verdict that supports it rather than with an
    exception's message. It is not 4 — nothing failed to arrive — and not 6,
    because nothing was proven false.
    """
    bundle = deepcopy(BY_NAME["v1_intact_range"])
    damage_it, condition = UNJUDGEABLE[damage]
    damage_it(bundle)
    verdict = verify_export(bundle)
    assert verdict.overall is Rederivation.unverifiable
    assert verdict.chain.condition is condition

    path = tmp_path / "unjudgeable.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code, stdout, stderr = run("--file", str(path), *(["--json"] if as_json else []))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stderr == "", "a verdict is an answer; nothing about it belongs on the error stream"
    if as_json:
        assert json.loads(stdout)["result"] == {
            "served": bundle["verification"],
            "local_check": verdict.to_document(),
        }
    else:
        assert stdout.startswith("local_check: unverifiable\n")
        assert f"chain: {condition}\n" in stdout


@pytest.mark.parametrize("damage", ["principal", "instant"])
def test_an_unjudgeable_entry_is_named_by_its_sequence_and_its_recipe(tmp_path: Path, damage):
    """« Unverifiable » alone is « something is wrong somewhere ».

    The two shapes where the verifier can say exactly which entry stopped it —
    a delegation that is not a chain, an instant outside the calendar — carry
    the sequence and the recipe that was being applied, and the prose renders
    both. Without them a reader has a non-zero exit and nowhere to look, which
    is an absence rendered as a fact (article 2).
    """
    bundle = deepcopy(BY_NAME["v1_intact_range"])
    UNJUDGEABLE[damage][0](bundle)
    verdict = verify_export(bundle)
    path = tmp_path / "unjudgeable.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    code, stdout, stderr = run("--file", str(path))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert f"chain.sequence: {verdict.chain.sequence}\n" in stdout
    assert f"chain.version: {verdict.chain.version}\n" in stdout
    assert verdict.chain.sequence == 1
    assert stderr == ""


def test_a_grade_the_reader_cannot_keep_is_passed_over_and_never_invented(tmp_path: Path):
    """The one shape whose chain is intact, and the one the client renders identically.

    A grade entry naming no connection and no grade is an assertion this reader
    cannot keep; the verifier passes over it rather than inventing one, so the
    verdict differs from the sound bundle's in `asserted_grades` alone. What the
    client must not do is turn that into a claim of its own, and what it cannot
    do is tell the reader which grade was dropped — the verdict does not say,
    and this client does not guess.
    """
    sound = deepcopy(BY_NAME["v1_intact_range"])
    damaged = deepcopy(sound)
    UNJUDGEABLE["asserted_grade"][0](damaged)
    assert verify_export(sound).asserted_grades
    assert verify_export(damaged).asserted_grades == {}
    path = tmp_path / "grades.json"
    path.write_text(json.dumps(damaged), encoding="utf-8")
    code, stdout, stderr = run("--file", str(path), "--json")
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert json.loads(stdout)["result"]["local_check"]["asserted_grades"] == {}
    assert stderr == ""
