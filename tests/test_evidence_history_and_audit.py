# SPDX-License-Identifier: Apache-2.0
"""Evidence reads through the command tree and a canned daemon, using published entries."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from canned_daemon import answering_by_path
from documents import arguments, chain_page_nested, entry_lines, evidence_page, problem
from sayfirst_contract.evidence import ChainCondition, verify_chain
from sayfirst_contract.generation import CONTRACT_GENERATION

from sayfirst_cli import exit_codes
from sayfirst_cli.main import main


def run(command, *argv, out=None):
    out, err = out if out is not None else io.StringIO(), io.StringIO()
    code = main(["evidence", command, *argv], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


@pytest.mark.parametrize("all_pages", [False, True])
@pytest.mark.parametrize("as_json", [False, True])
def test_history_reads_one_or_all_pages_in_served_order(
    tmp_path: Path, entries, all_pages, as_json
):
    pages = [evidence_page(entries[:2], next_from=3), evidence_page(entries[2:], from_sequence=3)]
    pages[0]["future_member"] = {"preserve": [True, None]}
    extra = [*(["--all"] if all_pages else []), *(["--json"] if as_json else [])]
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, pages)}) as address:
        code, stdout, stderr = run("history", *arguments(address, *extra))
    assert code == 0
    assert stderr == ""
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["result"] == {"pages": pages if all_pages else pages[:1]}
        assert envelope["verification"]["verified"] is True
    else:
        assert stdout.splitlines() == [
            *entry_lines(entries if all_pages else entries[:2]),
            f"next_from: {'none' if all_pages else 3}",
        ]


def test_history_prints_every_entry_and_the_end(tmp_path: Path, entries):
    with answering_by_path(
        tmp_path / "d.sock", {"/scopes/": (200, evidence_page(entries))}
    ) as address:
        code, stdout, stderr = run("history", *arguments(address))
    assert code == 0
    assert stdout.splitlines() == [*entry_lines(entries), "next_from: none"]
    assert stderr == ""


@pytest.mark.parametrize("as_json", [False, True])
def test_audit_merges_every_served_verdict_and_checks_all_entries(tmp_path: Path, entries, as_json):
    """Asserted metadata is rendered from the pages, never re-derived by the CLI: gaps
    in page order, a grade per connection with the later page's winning, and the count
    of pages the verdict is made of. `daemon` was graded on page 1 only and survives."""
    pages = [
        evidence_page(entries[:2], next_from=3),
        evidence_page(entries[2:], from_sequence=3, verified_entries=entries),
    ]
    pages[-1]["verification"]["declared_gaps"] = [{"sequence": 2, "reason": "purged", "count": 4}]
    pages[-1]["verification"]["grades"] = [{"connection_id": "connection-1", "grade": "evidence"}]
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, pages)}) as address:
        code, stdout, stderr = run("audit", *arguments(address, *(["--json"] if as_json else [])))
    assert code == 0
    assert stderr == ""
    if as_json:
        # Every member of `served` is one the plane's verifications carry; the
        # count of pages is this client's and travels beside it.
        assert json.loads(stdout)["result"] == {
            "served": {
                **pages[-1]["verification"],
                "declared_gaps": [{"sequence": 2, "reason": "purged", "count": 4}],
                "grades": [
                    {"connection_id": "connection-1", "grade": "evidence"},
                    {"connection_id": "daemon", "grade": "unverified"},
                ],
            },
            "local_check": verify_chain(entries, scope="local", from_sequence=1).to_document(),
            "pages": 2,
        }
    else:
        assert stdout.splitlines() == [
            "verification: intact",
            "pages: 2",
            "local_check: intact",
            "gap: sequence 2 reason purged count 4",
            "grade: connection-1 evidence",
            "grade: daemon unverified",
        ]
    assert "finding:" not in stdout


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("local_agrees", [True, False])
def test_audit_renders_a_gap_declared_on_an_earlier_page(
    tmp_path: Path, entries, as_json, local_agrees
):
    """The daemon verifies each page over that page's own range, so a purge declared
    before `next_from` cannot appear in the next page's verdict. Rendering only the
    last page's verdict printed no `gap:` line and exited 0 over a drop the plane had
    declared — an absence rendered as a healthy state (article 2)."""
    gap = {"sequence": 2, "reason": "purged", "count": 7}
    pages = [
        evidence_page(entries[:2], next_from=3),
        evidence_page(entries[2:], from_sequence=3, verified_entries=entries),
    ]
    pages[0]["verification"]["declared_gaps"] = [gap]
    if not local_agrees:
        # The plane says the chain broke where the local check finds it intact.
        pages[0]["verification"].update(condition="broken_at", sequence=2)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, pages)}) as address:
        code, stdout, stderr = run("audit", *arguments(address, *(["--json"] if as_json else [])))
    assert stderr == ""
    if as_json:
        result = json.loads(stdout)["result"]
        assert result["served"]["declared_gaps"] == [gap]
        assert result["served"]["condition"] == ("intact" if local_agrees else "broken_at")
        assert result["pages"] == 2
        assert "pages" not in result["served"]
        # The range is the whole read's, never one page's beside gaps from another.
        served = result["served"]
        assert served["from_sequence"] == pages[0]["verification"]["from_sequence"]
        # `up_to` belongs to the page whose condition is reported, never the last page's.
        reported = pages[0] if not local_agrees else pages[1]
        assert served["up_to"] == reported["verification"]["up_to"]
        assert served["covers_an_entry"] == any(
            page["verification"]["covers_an_entry"] for page in pages
        )
    else:
        assert "gap: sequence 2 reason purged count 7\n" in stdout
        assert "pages: 2\n" in stdout
    if local_agrees:
        assert code == 0
        assert "finding:" not in stdout
    else:
        # The first page that was not intact is the verdict the merge reports,
        # and the local check contradicts it: a finding, exit 6.
        assert code == exit_codes.EXIT_CHECK_FAILED
        if not as_json:
            assert "verification: broken_at\nverification.sequence: 2\n" in stdout
            assert "finding: the plane says broken_at, the local check says intact\n" in stdout


def test_changed_body_is_a_local_finding_never_a_replacement_verdict(tmp_path: Path, entries):
    document = evidence_page(entries)
    document["entries"][1]["body"]["grade"] = "evidence"
    local = verify_chain(document["entries"], scope="local", from_sequence=1)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, document)}) as address:
        code, stdout, stderr = run("audit", *arguments(address))
    assert code == exit_codes.EXIT_CHECK_FAILED
    assert stdout.startswith(
        "verification: intact\nlocal_check: broken_at\nlocal_check.sequence: 2\n"
        f"local_check.expected: {local.expected}\nlocal_check.found: {local.found}\n"
    )
    assert "finding: the plane says intact, the local check says broken_at\n" in stdout
    assert stderr == ""


def test_audit_ignores_corruption_after_the_bound_within_a_page(tmp_path: Path, entries):
    document = evidence_page(entries)
    document["entries"][2]["body"]["outcome"] = "allow"
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, document)}) as address:
        code, stdout, stderr = run("audit", *arguments(address, "--to", "2"))
    assert code == 0
    assert "verification: intact\nlocal_check: intact\n" in stdout
    assert "local_check.sequence:" not in stdout
    assert "finding:" not in stdout
    assert stderr == ""


@pytest.mark.parametrize("as_json", [False, True])
def test_an_entry_the_recipe_cannot_be_applied_to_is_a_local_check_and_never_a_non_answer(
    tmp_path: Path, entries, as_json
):
    """An instant outside the calendar: exit 7, a verdict, and no « could not ask ».

    The daemon answered, and the page it served is one this client read; what it
    could not do is judge the chain that page carries. Those are different
    facts, and the second is « could not check » — the verdict is rendered as the
    answer it is, with the sequence and the recipe beside it, and the disagreement
    with the served verdict is named as a finding. Reporting it as 4 said the
    plane could not be asked about a page this client was holding.
    """
    document = evidence_page(entries)
    document["entries"][0]["recorded_at"] = "0001-01-01T00:00:00+01:00"
    local = verify_chain(document["entries"], scope="local", from_sequence=1)
    assert local.condition is ChainCondition.unverifiable
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, document)}) as address:
        code, stdout, stderr = run("audit", *arguments(address, *(["--json"] if as_json else [])))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert code != exit_codes.EXIT_COULD_NOT_ASK
    assert stderr == ""
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["result"]["local_check"] == local.to_document()
        assert envelope["verification"]["verified"] is True
    else:
        assert "local_check: unverifiable\n" in stdout
        assert f"local_check.sequence: {local.sequence}\n" in stdout
        assert "finding: the plane says intact, the local check says unverifiable\n" in stdout
        assert "Traceback" not in stdout


def test_an_unknown_recipe_is_an_absence_and_never_a_break(tmp_path: Path, entries):
    """`unverifiable` at the sequence, naming the recipe — not `broken_at`, and not 6.

    `broken_at` is a negative fact the verifier established: it recomputed a
    hash and the number did not match. This verifier holds no reader for the
    recipe the last entry declares, so it recomputed nothing and established
    nothing — and exit 6 is published as « a finding this client made ». The
    verdict is the contract's to give and this client renders it, which is why
    the recipe's own name reaches the prose: it is the one thing a reader can
    act on.
    """
    document = evidence_page(entries)
    document["entries"][-1]["preimage_version"] = "sayfirst-control-plane/evidence/v9"
    local = verify_chain(document["entries"], scope="local", from_sequence=1)
    assert local.condition is ChainCondition.unverifiable
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, document)}) as address:
        code, stdout, stderr = run("audit", *arguments(address))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert code != exit_codes.EXIT_CHECK_FAILED
    assert "verification: intact\n" in stdout
    assert "local_check: unverifiable\nlocal_check.sequence: 3\n" in stdout
    assert "local_check.version: sayfirst-control-plane/evidence/v9\n" in stdout
    assert "finding: the plane says intact, the local check says unverifiable\n" in stdout
    assert stderr == ""


@pytest.mark.parametrize("command", ["history", "audit"])
@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    ("status", "problem_code", "expected"),
    [
        (403, "peer_not_admitted", exit_codes.EXIT_REFUSED),
        (503, "evidence_store_unavailable", exit_codes.EXIT_COULD_NOT_ASK),
    ],
)
def test_second_page_failure_names_where_it_stopped(
    tmp_path: Path, entries, command, as_json, status, problem_code, expected
):
    first = evidence_page(entries[:2], next_from=3)
    routes = {
        "/scopes/": (200, [first]),
        f"/scopes/local/evidence?contract_generation={CONTRACT_GENERATION}&from_sequence=3&": (
            status,
            problem(problem_code),
        ),
    }
    with answering_by_path(tmp_path / "d.sock", routes) as address:
        code, stdout, stderr = run(
            command,
            *arguments(
                address,
                *(["--all"] if command == "history" else []),
                *(["--json"] if as_json else []),
            ),
        )
    assert code == expected
    assert "local_check:" not in stdout
    assert problem_code in stderr
    assert "from_sequence 3" in stderr
    if as_json:
        envelope = json.loads(stderr)
        assert envelope["problem"]["code"] == problem_code
        assert envelope["verification"]["verified"] is True
    elif command == "history":
        assert stdout.splitlines() == entry_lines(entries[:2])
    else:
        assert stdout == ""


@pytest.mark.parametrize("argv", [[], ["unknown"]])
def test_evidence_requires_an_implemented_subcommand(argv):
    with pytest.raises(SystemExit) as failure:
        main(["evidence", *argv])
    assert failure.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["history", "--socket", "d.sock", "--from", "1"],
        ["history", "--scope", "local", "--from", "1"],
        ["history", "--scope", "local", "--socket", "d.sock"],
        ["audit", "--socket", "d.sock", "--from", "1"],
        ["audit", "--scope", "local", "--from", "1"],
        ["audit", "--scope", "local", "--socket", "d.sock"],
    ],
)
def test_online_reads_require_scope_socket_and_from(argv):
    with pytest.raises(SystemExit) as failure:
        main(["evidence", *argv])
    assert failure.value.code == 2


@pytest.mark.parametrize("page_size", ["0", "101", "-1"])
def test_history_rejects_page_sizes_outside_the_contract(page_size):
    with pytest.raises(SystemExit) as failure:
        run("history", *arguments("d.sock", "--page-size", page_size))
    assert failure.value.code == 2


@pytest.mark.parametrize("command", ["history", "audit"])
def test_two_pages_are_walked_against_a_daemon_that_closes_after_every_answer(
    tmp_path: Path, entries, command
):
    """A real daemon may hang up after an answer, and the transport never re-dials an
    address on a caller's behalf (rule C4). Both walks therefore reconnect before each
    page, and both have to finish over a connection that closes every time."""
    pages = [
        evidence_page(entries[:2], next_from=3),
        evidence_page(entries[2:], from_sequence=3, verified_entries=entries),
    ]
    routes = {"/scopes/": (200, pages)}
    with answering_by_path(tmp_path / "d.sock", routes, close_after_each=True) as address:
        code, stdout, stderr = run(
            command, *arguments(address, *(["--all"] if command == "history" else []))
        )
    assert stderr == ""
    assert code == 0
    if command == "history":
        assert stdout.splitlines() == [*entry_lines(entries), "next_from: none"]
    else:
        assert "verification: intact\npages: 2\nlocal_check: intact\n" in stdout


# --- one depth rule, measured where the render happens ---------------------


@pytest.mark.parametrize("command", ["history", "audit"])
def test_a_page_at_the_bound_is_rendered_and_not_refused_after_half_a_render(
    tmp_path: Path, command
):
    """A page exactly at the answer's bound is an answer, not a refusal.

    The floor under the two tests below: the page bound is the render's bound
    less the two levels the answer adds, and this is the depth where the
    subtraction has to leave a document that still goes all the way through. A
    bound tightened by one more level would fail here and nowhere else.
    """
    page = chain_page_nested(levels=64, next_from=None)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, page)}) as address:
        code, stdout, stderr = run(command, *arguments(address, "--json"))
    assert code == 0, stderr
    assert json.loads(stdout)["result"]


@pytest.mark.parametrize("command", ["history", "audit"])
@pytest.mark.parametrize("levels", [65, 66, 200])
def test_a_page_past_the_bound_is_refused_before_anything_is_written(
    tmp_path: Path, command, levels
):
    """The page validator bounds ONE page; `finish` then bounds the whole answer.

    `_online` hands `finish` `{"pages": [page, …]}`, so every page sits three
    levels down, and a page the validator accepted at 62 to 64 levels of its own
    was refused by the render at 64 to 66 levels of the answer's — after the
    prose for the pages before it had already reached stdout. Half an answer and
    then exit 4 is worse than either answer alone. 65 and 66 are the two depths
    that shape covered; 200 is past both bounds and was already refused.
    """
    page = chain_page_nested(levels=levels, next_from=None)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, page)}) as address:
        code, stdout, stderr = run(command, *arguments(address, "--json"))
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == "", "a refused answer wrote part of itself first"
    assert json.loads(stderr)["problem"]["code"] == "answer_unreadable"


@pytest.mark.parametrize("levels", [65, 66])
def test_the_prose_render_writes_no_entry_of_an_answer_it_will_refuse(tmp_path: Path, levels):
    """The prose path is the one that wrote half an answer: `history` prints the
    entries of each page as it walks it, so a bound read after the writing is a
    bound read too late. Measured before the fix: every entry of the page on
    stdout, then exit 4 on stderr, for a page nobody could act on either way."""
    page = chain_page_nested(levels=levels, next_from=None)
    with answering_by_path(tmp_path / "d.sock", {"/scopes/": (200, page)}) as address:
        code, stdout, stderr = run("history", *arguments(address))
    assert code == exit_codes.EXIT_COULD_NOT_ASK
    assert stdout == "", "the entries of a refused answer reached stdout"
    assert "not a page this client reads" in stderr
