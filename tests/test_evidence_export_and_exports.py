# SPDX-License-Identifier: Apache-2.0
"""Save served evidence unchanged and check bundles without a daemon."""

from __future__ import annotations

import io
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from canned_daemon import answering_by_path
from replies import Replies, verified
from sayfirst_contract.artifacts import load_json
from sayfirst_contract.evidence import verify_export
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.transport.socket_client import VerifiedConnection

from sayfirst_cli import exit_codes, reads
from sayfirst_cli.evidence import exit_for
from sayfirst_cli.main import main

VECTORS = {
    vector["name"]: vector["bundle"]
    for vector in load_json("domain", "evidence-export-manifest-vectors.json")["vectors"]
}


def bundle(name="v1_intact_range"):
    return {**deepcopy(VECTORS[name]), "contract_version": str(CONTRACT_GENERATION)}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = main(["evidence", *argv], out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def export_arguments(path, address, *extra):
    return (
        "export",
        "--scope",
        "local",
        "--socket",
        str(address),
        "--from",
        "1",
        "--out",
        str(path),
        *extra,
    )


@pytest.fixture(params=["memory", "socket"])
def daemon(request, tmp_path, monkeypatch):
    @contextmanager
    def arrange(status, document):
        if request.param == "socket":
            routes = {"/scopes/local/evidence/export?": (status, document)}
            with answering_by_path(tmp_path / "d.sock", routes) as address:
                yield address, None
        else:
            http = Replies([(status, document)])

            def connect(profile):
                assert profile.scope == "local"
                assert profile.socket_path == "daemon.sock"
                return verified(profile, http)

            monkeypatch.setattr(reads, "connect", connect)
            yield "daemon.sock", http

    return arrange


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("to_sequence", [None, 3])
def test_export_saves_the_served_document_and_renders_the_offline_check(
    tmp_path, daemon, as_json, to_sequence
):
    served = bundle()
    path = tmp_path / "saved.json"
    extra = ["--json"] if as_json else []
    if to_sequence is not None:
        extra.extend(["--to", str(to_sequence)])
    with daemon(200, served) as (address, http):
        code, stdout, stderr = run(*export_arguments(path, address, *extra))
    assert json.loads(path.read_text(encoding="utf-8")) == served
    assert path.read_bytes() == (json.dumps(served, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    assert stderr == ""
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["result"] == {
            "saved": str(path),
            "served": served["verification"],
            "local_check": verify_export(served).to_document(),
        }
        assert envelope["contract_generation"] == CONTRACT_GENERATION
        assert envelope["verification"]["verified"] is True
    else:
        _, audit_stdout, audit_stderr = run("audit", "--file", str(path))
        assert audit_stderr == ""
        assert stdout == audit_stdout + f"saved: {path} (3 entries)\n"
    if http is not None:
        target = (
            f"/scopes/local/evidence/export?contract_generation={CONTRACT_GENERATION}"
            "&from_sequence=1"
        )
        if to_sequence is not None:
            target += "&to_sequence=3"
        assert http.requests == [("GET", target, None)]
        assert http.closed
    # The served document is a published manifest vector: a minimal bundle the
    # contract's own verifier judges `unverifiable` (no policy attachments, no
    # decisions), so the offline check after saving is « could not check », 7 —
    # never a false 0. The mapping is the one function `exit_for`.
    assert code == exit_for(verify_export(served))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK


@pytest.mark.parametrize("kind", ["file", "directory", "dangling-symlink"])
@pytest.mark.parametrize("as_json", [False, True])
def test_existing_output_is_misuse_before_any_connection(tmp_path, no_socket, kind, as_json):
    path = tmp_path / "existing.json"
    if kind == "file":
        path.write_text("keep this", encoding="utf-8")
    elif kind == "directory":
        path.mkdir()
    else:
        path.symlink_to(tmp_path / "absent-target")
    code, stdout, stderr = run(
        *export_arguments(path, tmp_path / "absent.sock", *(["--json"] if as_json else []))
    )
    assert code == exit_codes.EXIT_MISUSE
    assert stdout == ""
    assert str(path) in stderr
    if kind == "file":
        assert path.read_text(encoding="utf-8") == "keep this"
    elif kind == "directory":
        assert path.is_dir()
    else:
        assert path.is_symlink()
        assert not (tmp_path / "absent-target").exists()


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    ("status", "problem_code", "expected"),
    [
        (403, "peer_not_admitted", exit_codes.EXIT_REFUSED),
        (503, "decision_store_unavailable", exit_codes.EXIT_COULD_NOT_ASK),
    ],
)
def test_unanswered_export_writes_no_file(
    tmp_path, daemon, as_json, status, problem_code, expected
):
    path = tmp_path / "not-saved.json"
    problem = {
        "contract_generation": CONTRACT_GENERATION,
        "code": problem_code,
        "message": "the requested read could not be answered",
        "retryable": False,
    }
    with daemon(status, problem) as (address, http):
        code, stdout, stderr = run(
            *export_arguments(path, address, *(["--json"] if as_json else []))
        )
    assert code == expected
    assert not path.exists()
    assert stdout == ""
    assert problem_code in stderr
    if as_json:
        envelope = json.loads(stderr)
        assert envelope["problem"] == problem
        assert envelope["verification"]["verified"] is True
        assert "result" not in envelope
    else:
        kind = "refused" if expected == exit_codes.EXIT_REFUSED else "could not ask"
        assert f"{kind}: {problem_code}:" in stderr
    if http is not None:
        assert http.closed


def save(directory, name, document):
    (directory / name).write_text(json.dumps(document), encoding="utf-8")


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("with_broken", [False, True])
def test_exports_lists_vectors_in_name_order_and_checks_them_offline(
    tmp_path, no_socket, as_json, with_broken
):
    intact = bundle()
    broken = bundle("v2_broken_chain")
    if with_broken:
        save(tmp_path, "notes.json", {"hello": 1})
        save(tmp_path, "b-broken.json", broken)
    save(tmp_path, "a-intact.json", intact)
    # Only JSON files in this directory participate.
    (tmp_path / "ignored.txt").write_text("not JSON", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    save(tmp_path / "nested", "nested.json", broken)
    code, stdout, stderr = run("exports", str(tmp_path), *(["--json"] if as_json else []))
    assert stderr == ""
    documents = [("a-intact.json", intact)]
    if with_broken:
        documents.append(("b-broken.json", broken))
    if as_json:
        envelope = json.loads(stdout)
        expected = [
            {
                "file": name,
                "scope": document["scope"],
                "from_sequence": document["from_sequence"],
                "to_sequence": document.get("to_sequence"),
                "served": document["verification"],
                "local_check": verify_export(document).to_document(),
            }
            for name, document in documents
        ]
        if with_broken:
            expected.append({"file": "notes.json", "not_a_bundle": True})
        assert envelope["result"] == {"directory": str(tmp_path), "bundles": expected}
        assert envelope["verification"] == {
            "server_uid": None,
            "expected": None,
            "verified": False,
        }
    else:
        expected = [
            f"{name} local 1..3 served:{document['verification']['condition']} "
            f"local:{verify_export(document).overall}"
            for name, document in documents
        ]
        if with_broken:
            expected.append("notes.json not a bundle")
        assert stdout.splitlines() == expected
    # Every published vector is a minimal bundle the verifier judges
    # `unverifiable` — the broken one too, because that verdict takes precedence
    # (requirement 5) — so a directory of vectors is « could not check », 7.
    # The aggregation rule (any 6 → 6, else any 7 → 7, else 0) is what is
    # asserted; the vectors happen to exercise its middle branch.
    codes = [exit_for(verify_export(document)) for _, document in documents]
    assert codes and set(codes) == {exit_codes.EXIT_COULD_NOT_CHECK}
    expected_code = (
        exit_codes.EXIT_CHECK_FAILED
        if exit_codes.EXIT_CHECK_FAILED in codes
        else exit_codes.EXIT_COULD_NOT_CHECK
        if exit_codes.EXIT_COULD_NOT_CHECK in codes
        else 0
    )
    assert code == expected_code == exit_codes.EXIT_COULD_NOT_CHECK


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize("default_directory", [False, True])
def test_empty_exports_directory(tmp_path, no_socket, monkeypatch, as_json, default_directory):
    monkeypatch.chdir(tmp_path)
    directory = "." if default_directory else str(tmp_path)
    code, stdout, stderr = run(
        "exports",
        *([] if default_directory else [directory]),
        *(["--json"] if as_json else []),
    )
    assert code == 0
    assert stderr == ""
    if as_json:
        assert json.loads(stdout)["result"] == {"directory": directory, "bundles": []}
    else:
        assert stdout == f"no bundles in {directory}\n"


@pytest.mark.parametrize("contents", ["{broken", "[]", '{"hello": 1}', "\udcff"])
def test_exports_marks_non_bundles_without_failing(tmp_path, no_socket, contents):
    (tmp_path / "notes.json").write_bytes(contents.encode("utf-8", errors="surrogateescape"))
    code, stdout, stderr = run("exports", str(tmp_path))
    assert code == 0
    assert stdout == "notes.json not a bundle\n"
    assert stderr == ""


@pytest.mark.parametrize("extra", [("--scope", "local"), ("--socket", "absent.sock")])
def test_exports_rejects_connection_arguments(tmp_path, no_socket, extra):
    with pytest.raises(SystemExit) as failure:
        run("exports", str(tmp_path), *extra)
    assert failure.value.code == 2


@pytest.mark.parametrize("extra", [("--from", "0"), ("--from", "3", "--to", "2")])
def test_export_rejects_invalid_ranges(tmp_path, no_socket, extra):
    with pytest.raises(SystemExit) as failure:
        run(*export_arguments(tmp_path / "out.json", "absent.sock", *extra))
    assert failure.value.code == 2


@pytest.mark.parametrize("missing", ["--scope", "--socket", "--from", "--out"])
def test_export_requires_its_arguments(tmp_path, no_socket, missing):
    arguments = list(export_arguments(tmp_path / "out.json", "absent.sock"))
    index = arguments.index(missing)
    del arguments[index : index + 2]
    with pytest.raises(SystemExit) as failure:
        run(*arguments)
    assert failure.value.code == 2


def test_export_checks_the_received_object_after_saving_without_rereading(tmp_path, monkeypatch):
    from sayfirst_cli import evidence

    served = bundle()
    path = tmp_path / "saved.json"
    real_read = VerifiedConnection.export_evidence
    received = []

    def read(connection, scope, from_sequence, to_sequence):
        result = real_read(connection, scope, from_sequence, to_sequence)
        received.append(result.value)
        return result

    def verify(document):
        assert path.is_file(), "the document must be saved before it is checked"
        assert document is received[0], "check the object returned by the transport"
        return verify_export(document)

    def forbidden(*args, **kwargs):
        pytest.fail("export must not reread the saved file")

    http = Replies([(200, served)])
    monkeypatch.setattr(
        reads,
        "connect",
        lambda profile: verified(profile, http),
    )
    monkeypatch.setattr(VerifiedConnection, "export_evidence", read)
    monkeypatch.setattr(evidence, "verify_export", verify)
    monkeypatch.setattr(Path, "read_text", forbidden)
    code, stdout, stderr = run(*export_arguments(path, "daemon.sock", "--from", "2", "--json"))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stderr == ""
    assert json.loads(stdout)["result"]["local_check"] == verify_export(served).to_document()
    assert http.requests == [
        (
            "GET",
            f"/scopes/local/evidence/export?contract_generation={CONTRACT_GENERATION}"
            "&from_sequence=2",
            None,
        )
    ]
    assert http.closed


def test_export_never_overwrites_a_file_created_during_the_read(tmp_path, monkeypatch):
    path = tmp_path / "raced.json"

    def responses():
        path.write_text("another writer", encoding="utf-8")
        yield 200, bundle()

    http = Replies(responses())
    monkeypatch.setattr(
        reads,
        "connect",
        lambda profile: verified(profile, http),
    )
    code, stdout, stderr = run(*export_arguments(path, "daemon.sock"))
    assert code == exit_codes.EXIT_MISUSE
    assert stdout == ""
    assert str(path) in stderr
    assert path.read_text(encoding="utf-8") == "another writer"
    assert http.closed


@pytest.mark.parametrize("as_json", [False, True])
def test_exports_reports_open_range_and_absent_served_verification(tmp_path, no_socket, as_json):
    document = bundle()
    del document["verification"]
    del document["to_sequence"]
    save(tmp_path, "open.json", document)
    code, stdout, stderr = run("exports", str(tmp_path), *(["--json"] if as_json else []))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stderr == ""
    if as_json:
        assert json.loads(stdout)["result"]["bundles"] == [
            {
                "file": "open.json",
                "scope": "local",
                "from_sequence": 1,
                "to_sequence": None,
                "served": None,
                "local_check": verify_export(document).to_document(),
            }
        ]
    else:
        assert stdout == "open.json local 1..open served:none local:unverifiable\n"


@pytest.mark.parametrize("failed_first", [False, True])
def test_exports_check_failed_precedes_could_not_check(tmp_path, no_socket, failed_first):
    differs = bundle("v3_closed_epoch_with_present_policy")
    save(tmp_path, "a.json" if failed_first else "b.json", differs)
    save(tmp_path, "b.json" if failed_first else "a.json", bundle())
    code, stdout, stderr = run("exports", str(tmp_path))
    assert code == exit_codes.EXIT_CHECK_FAILED
    assert "local:differs\n" in stdout
    assert "local:unverifiable\n" in stdout
    assert stderr == ""


@pytest.mark.parametrize("as_json", [False, True])
def test_exports_missing_directory_is_could_not_check(tmp_path, no_socket, as_json):
    path = tmp_path / "absent"
    code, stdout, stderr = run("exports", str(path), *(["--json"] if as_json else []))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stdout == ""
    assert str(path) in stderr
    if as_json:
        assert json.loads(stderr)["problem"]["code"] == "answer_unreadable"
    else:
        assert "could not check:" in stderr


@pytest.mark.parametrize("as_json", [False, True])
def test_exports_lists_a_bundle_it_could_not_judge_with_its_verdict(tmp_path, no_socket, as_json):
    """A listing states what each entry IS, and « unverifiable » is a verdict.

    This bundle's delegation is not a chain, so the verifier established nothing
    about its chain and says so. It used to raise, and the listing then had a
    file it could not check and no verdict to show for it; now the entry carries
    the verdict like every other, the run exits 7 because the check did not
    conclude, and nothing goes to the error stream — a verdict is an answer.

    « Could not check » remains an item shape and is still proven, on the file
    this client genuinely cannot read: see the unreadable-file test below.
    """
    document = bundle()
    document["entries"][0]["principal"]["via"] = [None]
    save(tmp_path, "unjudgeable.json", document)
    code, stdout, stderr = run("exports", str(tmp_path), *(["--json"] if as_json else []))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stderr == ""
    if as_json:
        item = json.loads(stdout)["result"]["bundles"][0]
        assert item["file"] == "unjudgeable.json"
        assert item["local_check"] == verify_export(document).to_document()
        assert "not_a_bundle" not in item and "could_not_check" not in item
    else:
        assert stdout == "unjudgeable.json local 1..3 served:intact local:unverifiable\n"


@pytest.mark.parametrize("as_json", [False, True])
def test_export_saves_the_bundle_and_reports_the_verdict_it_could_not_conclude(
    tmp_path, daemon, as_json
):
    """The bundle is saved and the check is reported, whatever the check concluded.

    The two halves are independent and both are asserted: what the daemon served
    reaches the file byte for byte, and the verdict this client could not
    conclude is rendered beside the saved path. Exit 7 — the answer arrived and
    the check did not conclude — never 4, and never a file saved without a word
    said about it.
    """
    served = bundle()
    served["entries"][0]["principal"]["via"] = [None]
    path = tmp_path / "saved.json"
    with daemon(200, served) as (address, _):
        code, stdout, stderr = run(
            *export_arguments(path, address, *(["--json"] if as_json else []))
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert code != exit_codes.EXIT_COULD_NOT_ASK
    assert json.loads(path.read_text(encoding="utf-8")) == served
    assert stderr == ""
    if as_json:
        envelope = json.loads(stdout)
        assert envelope["result"]["saved"] == str(path)
        assert envelope["result"]["local_check"] == verify_export(served).to_document()
        # The connection WAS verified before the ask; the envelope says so.
        assert envelope["verification"]["verified"] is True
    else:
        assert "local_check: unverifiable\n" in stdout
        assert f"saved: {path}" in stdout


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file")
@pytest.mark.parametrize("as_json", [False, True])
def test_exports_reports_an_unreadable_file_as_could_not_check(tmp_path, no_socket, as_json):
    """Unreadable is not « not a bundle »: the file may well be one (article 2)."""
    save(tmp_path, "secret.json", bundle())
    (tmp_path / "secret.json").chmod(0)
    try:
        code, stdout, stderr = run("exports", str(tmp_path), *(["--json"] if as_json else []))
    finally:
        (tmp_path / "secret.json").chmod(0o600)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert "Traceback" not in stderr
    if as_json:
        item = json.loads(stdout)["result"]["bundles"][0]
        assert item["file"] == "secret.json"
        assert "could_not_check" in item and "not_a_bundle" not in item
        assert stderr == ""
    else:
        assert "secret.json" in stderr
        assert stdout == "secret.json could not check\n"


def test_exports_never_escapes_on_a_pathologically_deep_file(tmp_path, no_socket):
    """A traceback would exit 1, the code for deny; a file too deep to parse is not a bundle."""
    (tmp_path / "deep.json").write_text("[" * 20000 + "]" * 20000, encoding="utf-8")
    code, stdout, stderr = run("exports", str(tmp_path))
    assert code == 0
    assert stdout == "deep.json not a bundle\n"
    assert "Traceback" not in stderr


@pytest.mark.parametrize("as_json", [False, True])
def test_exports_lists_a_directory_named_like_a_bundle_as_not_a_bundle(
    tmp_path, no_socket, as_json
):
    (tmp_path / "looks-like.json").mkdir()
    code, stdout, stderr = run("exports", str(tmp_path), *(["--json"] if as_json else []))
    assert code == 0 and stderr == ""
    if as_json:
        assert json.loads(stdout)["result"]["bundles"] == [
            {"file": "looks-like.json", "not_a_bundle": True}
        ]
    else:
        assert stdout == "looks-like.json not a bundle\n"


@pytest.mark.parametrize("as_json", [False, True])
def test_export_saves_then_reports_could_not_check_when_entries_are_missing(
    tmp_path, daemon, as_json
):
    """Every read of the saved bundle — the count rendered after the check included —
    sits inside the guard: a reply without `entries` is « could not check », not exit 4."""
    served = bundle()
    del served["entries"]
    path = tmp_path / "saved.json"
    with daemon(200, served) as (address, _):
        code, stdout, stderr = run(
            *export_arguments(path, address, *(["--json"] if as_json else []))
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert json.loads(path.read_text(encoding="utf-8")) == served
    assert str(path) in stderr and "saved" in stderr
    assert "Traceback" not in stderr
    assert stdout == ""


def test_export_refuses_an_out_path_it_cannot_look_at(tmp_path, no_socket):
    """A name too long to stat is misuse (64) before anything is asked — never a traceback."""
    path = tmp_path / ("x" * 300 + ".json")
    code, stdout, stderr = run(*export_arguments(path, "unused"))
    assert code == exit_codes.EXIT_MISUSE
    assert stdout == ""
    assert "cannot use:" in stderr and "Traceback" not in stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root searches any directory")
@pytest.mark.parametrize("as_json", [False, True])
def test_exports_reports_an_unsearchable_directory_entry_as_could_not_check(
    tmp_path, no_socket, as_json
):
    """A directory readable but not searchable lists its names and refuses their stat."""
    save(tmp_path, "bundle.json", bundle())
    tmp_path.chmod(0o600)
    try:
        code, stdout, stderr = run("exports", str(tmp_path), *(["--json"] if as_json else []))
    finally:
        tmp_path.chmod(0o700)
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert "Traceback" not in stderr
    if as_json:
        item = json.loads(stdout)["result"]["bundles"][0]
        assert item["file"] == "bundle.json" and "could_not_check" in item
        assert stderr == ""
    else:
        assert stdout == "bundle.json could not check\n"
        assert "bundle.json" in stderr


def test_exports_json_stays_one_envelope_however_many_entries_cannot_be_judged(tmp_path, no_socket):
    """Whatever each entry turns out to be, stdout is one document a reader parses.

    Two bundles neither of which can be judged: one envelope, both entries in it,
    each carrying its own verdict, and the run's exit made of them. A listing
    that wrote a second envelope, or a sentence between them, would be a stream
    a machine caller cannot read on exactly the runs it has to.
    """
    for name in ("one.json", "two.json"):
        document = bundle()
        document["entries"][0]["principal"]["via"] = [None]
        save(tmp_path, name, document)
    code, stdout, stderr = run("exports", str(tmp_path), "--json")
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stderr == ""
    items = json.loads(stdout)["result"]["bundles"]
    assert [item["file"] for item in items] == ["one.json", "two.json"]
    assert all(item["local_check"]["chain"]["condition"] == "unverifiable" for item in items)


def _deep_bundle_text(depth):
    return (
        '{"scope": "local", "from_sequence": 1, "entries": [], "manifest_hash": "x",'
        ' "verification": ' + "[" * depth + "]" * depth + "}"
    )


@pytest.mark.parametrize("depth", [200, 9993])
@pytest.mark.parametrize("as_json", [False, True])
def test_exports_declines_a_file_nested_beyond_the_limit(tmp_path, no_socket, depth, as_json):
    """A file that parses but nests beyond the limit is not a bundle in either mode. Depth
    9993 is the window measured on CPython where the parse succeeds and the JSON render of
    the envelope would recurse past the interpreter's limit — the escape this bound closes."""
    (tmp_path / "deep.json").write_text(_deep_bundle_text(depth), encoding="utf-8")
    code, stdout, stderr = run("exports", str(tmp_path), *(["--json"] if as_json else []))
    assert code == 0
    assert stderr == ""
    if as_json:
        assert json.loads(stdout)["result"]["bundles"] == [
            {"file": "deep.json", "not_a_bundle": True}
        ]
    else:
        assert stdout == "deep.json not a bundle\n"


@pytest.mark.parametrize("depth", [200, 9993])
@pytest.mark.parametrize("as_json", [False, True])
def test_offline_audit_declines_a_file_nested_beyond_the_limit(tmp_path, no_socket, depth, as_json):
    path = tmp_path / "deep.json"
    path.write_text(_deep_bundle_text(depth), encoding="utf-8")
    code, stdout, stderr = run("audit", "--file", str(path), *(["--json"] if as_json else []))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert stdout == ""
    assert "Traceback" not in stderr
    if as_json:
        problem = json.loads(stderr)["problem"]
        assert problem["code"] == "answer_unreadable"
        assert "deeper than" in problem["message"] or "recursion" in problem["message"].lower()
    else:
        assert "could not check:" in stderr


@pytest.mark.parametrize("as_json", [False, True])
def test_export_saves_then_declines_a_reply_nested_beyond_the_limit(tmp_path, daemon, as_json):
    """The daemon's reply is bounded like a file: saved, then « could not check » naming the
    saved path in both modes — never exit 4 with the file unreported when the envelope render
    would be the step that overflows."""
    served = bundle()
    served["verification"] = json.loads("[" * 200 + "]" * 200)
    path = tmp_path / "saved.json"
    with daemon(200, served) as (address, _):
        code, stdout, stderr = run(
            *export_arguments(path, address, *(["--json"] if as_json else []))
        )
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert json.loads(path.read_text(encoding="utf-8")) == served
    assert str(path) in stderr and "saved" in stderr and "deeper than" in stderr
    assert "Traceback" not in stderr
    assert stdout == ""


def test_export_finishes_against_a_daemon_that_closes_after_its_answer(tmp_path):
    """One read, and the far end hangs up after it. Nothing is read twice here, so rule
    C4 has nothing to refuse: the bundle is saved and the exit is the local check's."""
    served = bundle()
    path = tmp_path / "saved.json"
    routes = {"/scopes/local/evidence/export?": (200, served)}
    with answering_by_path(tmp_path / "d.sock", routes, close_after_each=True) as address:
        code, stdout, stderr = run(*export_arguments(path, address))
    assert json.loads(path.read_text(encoding="utf-8")) == served
    assert code == exit_for(verify_export(served))
    assert code == exit_codes.EXIT_COULD_NOT_CHECK
    assert f"saved: {path} (3 entries)\n" in stdout
    assert stderr == ""
