# SPDX-License-Identifier: Apache-2.0
"""Read evidence and render the contract's local checks beside the served verdicts."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Final, TextIO

from sayfirst_contract.client import Answered, CouldNotAsk, Refused, Result
from sayfirst_contract.evidence import (
    ChainCondition,
    ChainVerdict,
    ExportVerdict,
    Rederivation,
    verify_chain,
    verify_export,
)
from sayfirst_contract.generation import CONTRACT_GENERATION
from sayfirst_contract.problems import Problem, ProblemCode, problem_retryable
from sayfirst_contract.transport.socket_client import PER_USER, SYSTEM

from . import exit_codes, pages, reads, render


def exit_for(verdict: ChainVerdict | ExportVerdict) -> int:
    """One exit policy for the contract's chain and export verdicts.

    **A member this client does not know is read as « could not check »
    wherever one of the two tables below decides the answer, and never as a
    traceback.** A generation that adds a member to either vocabulary is one
    whose conclusion this client cannot render — which is a check it cannot
    perform, exactly what 7 is for. On the export path the contract's own
    `overall` governs, as it does for every chain condition that is not a
    finding: an unknown chain condition under a confirmed rederivation is not
    made to outrank the conclusion the contract gave, because this client
    renders verdicts and does not re-judge them. Read through `.get` rather than a
    subscript, because the alternative is a `KeyError` out of a read, and a
    traceback ends the process with exit 1, this client's published code for
    « the control plane answered deny ». Article 13 asks that an unknown value
    be read as unknown; this is that rule applied to the client's own reading of
    a verdict, and it is the direction an unknown has to fail in (article 2).

    The tables stay exhaustive over the members that exist, so a member this
    generation DOES define can never quietly take the fallback; nothing here is
    a list of conditions to keep in step with the contract.
    """
    if isinstance(verdict, ChainVerdict):
        return {
            ChainCondition.intact: 0,
            ChainCondition.broken_at: exit_codes.EXIT_CHECK_FAILED,
            ChainCondition.gap_at: exit_codes.EXIT_CHECK_FAILED,
            ChainCondition.unverifiable: exit_codes.EXIT_COULD_NOT_CHECK,
        }.get(verdict.condition, exit_codes.EXIT_COULD_NOT_CHECK)
    # Rederivation names the contract's conclusion: confirmed is success,
    # differs is a finding, and unverifiable cannot conclude. The latter and
    # an unknown manifest recipe take precedence over export failures.
    overall_exit = {
        Rederivation.confirmed: 0,
        Rederivation.differs: exit_codes.EXIT_CHECK_FAILED,
        Rederivation.unverifiable: exit_codes.EXIT_COULD_NOT_CHECK,
    }.get(verdict.overall, exit_codes.EXIT_COULD_NOT_CHECK)
    if verdict.manifest_hash_recomputes is None or overall_exit == exit_codes.EXIT_COULD_NOT_CHECK:
        return exit_codes.EXIT_COULD_NOT_CHECK
    if verdict.manifest_hash_recomputes is False or (
        verdict.chain is not None
        and verdict.chain.condition in (ChainCondition.broken_at, ChainCondition.gap_at)
    ):
        return exit_codes.EXIT_CHECK_FAILED
    return overall_exit


def _page_size(value: str) -> int:
    number = reads.positive(value)
    if number > 100:
        raise argparse.ArgumentTypeError("must be at most 100")
    return number


def _history(argv: Sequence[str], *, out: TextIO, err: TextIO) -> int:
    parser = argparse.ArgumentParser(prog="sayfirst evidence history")
    reads.add_connection_arguments(parser)
    parser.add_argument("--from", dest="from_sequence", type=reads.positive, required=True)
    parser.add_argument("--page-size", type=_page_size, default=100)
    parser.add_argument("--all", action="store_true", help="follow every continuation")
    return _online(parser.parse_args(argv), out, err, history=True)


def _audit(argv: Sequence[str], *, out: TextIO, err: TextIO) -> int:
    parser = argparse.ArgumentParser(prog="sayfirst evidence audit")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="check an export without opening a socket")
    source.add_argument("--socket", help="the path of the daemon's socket")
    parser.add_argument("--scope", help="the scope the question is asked in")
    parser.add_argument("--mode", choices=(PER_USER, SYSTEM), default=PER_USER)
    parser.add_argument("--daemon-user", default=None)
    parser.add_argument("--from", dest="from_sequence", type=reads.positive)
    parser.add_argument("--to", dest="to_sequence", type=reads.positive)
    parser.add_argument("--json", action="store_true", help="write the envelope instead of prose")
    arguments = parser.parse_args(argv)
    if arguments.file is not None:
        if arguments.scope is not None:
            parser.error("--file is not allowed with --scope")
        if arguments.from_sequence is not None or arguments.to_sequence is not None:
            parser.error("--from and --to require --socket")
        return _offline(arguments, out, err)
    if arguments.scope is None or arguments.from_sequence is None:
        parser.error("online audit requires --scope and --from")
    if arguments.to_sequence is not None and arguments.to_sequence < arguments.from_sequence:
        parser.error("--to must be at least --from")
    arguments.page_size = 100
    return _online(arguments, out, err, history=False)


def _export(argv: Sequence[str], *, out: TextIO, err: TextIO) -> int:
    parser = argparse.ArgumentParser(prog="sayfirst evidence export")
    reads.add_connection_arguments(parser)
    parser.add_argument("--from", dest="from_sequence", type=reads.positive, required=True)
    parser.add_argument("--to", dest="to_sequence", type=reads.positive)
    parser.add_argument("--out", required=True, help="save the served bundle to a new file")
    arguments = parser.parse_args(argv)
    if arguments.to_sequence is not None and arguments.to_sequence < arguments.from_sequence:
        parser.error("--to must be at least --from")
    path = Path(arguments.out)
    # Reject every existing directory entry, including a dangling symlink,
    # before verifying or reading from the daemon.
    try:
        taken = path.exists() or path.is_symlink()
    except OSError as failure:
        # A path this process cannot even look at (too long, in a directory
        # it may not search) is unusable, and nothing has been asked yet.
        err.write(f"cannot use: {arguments.out}: {failure}\n")
        return exit_codes.EXIT_MISUSE
    if taken:
        err.write(f"refusing to overwrite: {arguments.out}\n")
        return exit_codes.EXIT_MISUSE
    connection = reads.open_connection(arguments, err)
    if isinstance(connection, int):
        return connection
    try:
        # The reply is NOT bounded before it is saved: a bundle nested past the
        # bound is still the daemon's answer, and losing it to a rendering rule
        # would be this client deciding what may be kept. It is saved, then the
        # bound applies to the check below.
        result = reads.read(
            lambda: connection.export_evidence(
                arguments.scope, arguments.from_sequence, arguments.to_sequence
            )
        )
        if isinstance(result, Answered):
            bundle = result.value
            contents = json.dumps(bundle, sort_keys=True, indent=2) + "\n"
            try:
                # Exclusive creation also refuses a path created while the
                # read was in flight; the early check alone cannot do that.
                with path.open("x", encoding="utf-8") as saved:
                    saved.write(contents)
            except OSError as failure:
                err.write(f"could not save: {arguments.out}: {failure}\n")
                return exit_codes.EXIT_MISUSE
            try:
                # The bundle is saved either way. A verifier that cannot read
                # it is « could not check » — exit_codes.py keeps that apart
                # from « could not ask » — and the saved path is named, so a
                # file this command wrote is never left unreported.
                if reads.too_deep(bundle):
                    raise ValueError(
                        f"nested deeper than {reads.DOCUMENT_DEPTH_LIMIT} levels; "
                        "not a bundle this client reads"
                    )
                local = verify_export(bundle)
                served = bundle["verification"]
                count = len(bundle["entries"])
            except reads.INPUT_ERRORS as failure:
                return _could_not_check(
                    f"{arguments.out} (saved, not checked)",
                    failure,
                    arguments.json,
                    err,
                    verification=render.verification_document(
                        connection.server_credential.uid,
                        connection.expected_uid,
                        connection.verified,
                    ),
                )
            document = {
                "saved": arguments.out,
                "served": served,
                "local_check": local.to_document(),
            }

            def write_saved(document: Mapping[str, object], stream: TextIO) -> None:
                _write_export_check(bundle, local, stream)
                stream.write(f"saved: {document['saved']} ({count} entries)\n")

            reads.finish(
                Answered(document, CONTRACT_GENERATION),
                arguments,
                connection,
                out,
                err,
                write_saved,
            )
            return exit_for(local)
        return reads.finish(result, arguments, connection, out, err, render.write_record)
    finally:
        connection.close()


def _exports(argv: Sequence[str], *, out: TextIO, err: TextIO) -> int:
    """List every `*.json` file of a directory as what it is, and check the bundles.

    A listing states what each entry is, so a file that does not parse is
    listed as « not a bundle » and no check failed, while the same bytes named
    to `audit --file` answer « could not check »: there the check is the whole
    question, and one that could not run is not a bundle judged sound.
    """
    parser = argparse.ArgumentParser(prog="sayfirst evidence exports")
    parser.add_argument("directory", nargs="?", default=".")
    parser.add_argument("--json", action="store_true", help="write the envelope instead of prose")
    arguments = parser.parse_args(argv)
    bundles: list[dict[str, object]] = []
    codes: set[int] = set()
    try:
        paths = sorted(
            (path for path in Path(arguments.directory).iterdir() if path.name.endswith(".json")),
            key=lambda path: path.name,
        )
    except OSError as failure:
        return _could_not_check(arguments.directory, failure, arguments.json, err)
    for path in paths:
        try:
            regular = path.is_file()
        except OSError as failure:
            # The listing was readable but the entry is not even stat-able
            # (a directory without search permission): not a bundle is not
            # known, so this is « could not check ».
            _list_entry(
                bundles,
                out,
                path.name,
                as_json=arguments.json,
                reason=_could_not_check_entry(path, failure, arguments, err, codes),
            )
            continue
        if not regular:
            # A directory or a dangling link named like a bundle is listed,
            # never dropped: silence here would read as « no such file ».
            _list_entry(bundles, out, path.name, as_json=arguments.json, reason=None)
            continue
        try:
            data = path.read_bytes()
        except OSError as failure:
            # Unreadable is not « not a bundle »: the file may well be one, and
            # « I could not read it » is not a negative fact (article 2).
            _list_entry(
                bundles,
                out,
                path.name,
                as_json=arguments.json,
                reason=_could_not_check_entry(path, failure, arguments, err, codes),
            )
            continue
        try:
            # Bytes, so a file that is not even UTF-8 is « not a bundle »
            # (json.loads raises ValueError for it) rather than an escape.
            bundle = json.loads(data)
        except (ValueError, RecursionError):
            bundle = None
        if bundle is not None and reads.too_deep(bundle):
            bundle = None
        if not isinstance(bundle, Mapping) or not {
            "scope",
            "from_sequence",
            "entries",
            "manifest_hash",
        }.issubset(bundle):
            _list_entry(bundles, out, path.name, as_json=arguments.json, reason=None)
            continue
        try:
            local = verify_export(bundle)
        except reads.INPUT_ERRORS as failure:
            reason = _could_not_check_entry(path, failure, arguments, err, codes)
            local = None
        else:
            codes.add(exit_for(local))
            reason = None
        served = bundle.get("verification")
        item: dict[str, object] = {
            "file": path.name,
            "scope": bundle["scope"],
            "from_sequence": bundle["from_sequence"],
            "to_sequence": bundle.get("to_sequence"),
            "served": served,
            "local_check": local.to_document() if local is not None else None,
        }
        if reason is not None:
            item["could_not_check"] = reason
        bundles.append(item)
        if not arguments.json:
            to_sequence = bundle.get("to_sequence")
            condition = served.get("condition") if isinstance(served, Mapping) else None
            overall = local.overall if local is not None else render.NOT_STATED
            out.write(
                f"{path.name} {bundle['scope']} {bundle['from_sequence']}.."
                f"{to_sequence if to_sequence is not None else 'open'} "
                f"served:{condition if condition is not None else 'none'} local:{overall}\n"
            )
    if arguments.json:
        render.write_json(
            render.envelope(
                CONTRACT_GENERATION,
                render.verification_document(None, None, False),
                result={"directory": arguments.directory, "bundles": bundles},
            ),
            out,
        )
    elif not bundles:
        out.write(f"no bundles in {arguments.directory}\n")
    if exit_codes.EXIT_CHECK_FAILED in codes:
        return exit_codes.EXIT_CHECK_FAILED
    if exit_codes.EXIT_COULD_NOT_CHECK in codes:
        return exit_codes.EXIT_COULD_NOT_CHECK
    return 0


def _merged_verdict(verdicts: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """One served verdict for a read that spanned several pages, dropping nothing.

    The daemon verifies each page over that page's own range, so a purge it
    declared before a page's `from` cannot appear in that page's verdict.
    Rendering only the last page's verdict therefore drops what the plane said
    on every earlier one, and a declared drop rendered as a clean chain is an
    absence rendered as a healthy state, which article 2 forbids.

    So: declared gaps are concatenated in page order; a grade is kept per
    connection, a later page's replacing an earlier one; and the condition is
    `intact` only if every page said so. The first page that said otherwise is
    the one whose verdict is reported, its `sequence`, `expected` and `found`
    included, so that what is rendered beside the condition belongs to it.

    Every member of what comes back is a member the plane's own verifications
    carry. How many pages the answer is made of is this client's fact, not the
    plane's, so it is reported beside this document and never inside it — a
    member of `served` reads as something the daemon said (article 2).
    """
    base = next(
        (verdict for verdict in verdicts if verdict["condition"] != ChainCondition.intact.value),
        verdicts[-1],
    )
    gaps: list[object] = []
    grades: dict[object, object] = {}
    for verdict in verdicts:
        gaps.extend(verdict["declared_gaps"])
        for grade in verdict["grades"]:
            grades[grade["connection_id"]] = grade
    merged: dict[str, object] = {**base, "declared_gaps": gaps, "grades": list(grades.values())}
    # The range members describe the whole read, not the page the condition
    # came from: a gap declared at 2 inside a verdict claiming « from 3 » would
    # be a document no daemon sent, contradicting itself.
    # `up_to` stays with `base`: it means « verified intact through here » on
    # the page whose condition is reported, not the read's end.
    if "from_sequence" in base:
        merged["from_sequence"] = verdicts[0].get("from_sequence")
    if "to_sequence" in base:
        merged["to_sequence"] = next(
            (v["to_sequence"] for v in reversed(verdicts) if v.get("to_sequence") is not None),
            None,
        )
    if "covers_an_entry" in base:
        merged["covers_an_entry"] = any(v.get("covers_an_entry") is True for v in verdicts)
    return merged


def _write_entries(entries: Sequence[Mapping[str, object]], out: TextIO) -> None:
    for entry in entries:
        out.write(
            f"{entry['sequence']} {entry['kind']} {entry['connection_id']} {entry['entry_hash']}\n"
        )
    out.flush()


def _write_history(document: Mapping[str, object], out: TextIO) -> None:
    # Entries have already been written as each page arrived.
    next_from = document["pages"][-1]["next_from"]
    out.write(f"next_from: {'none' if next_from is None else next_from}\n")


def _write_audit(document: Mapping[str, object], out: TextIO) -> None:
    served, local = document["served"], document["local_check"]
    out.write(f"verification: {served['condition']}\n")
    if served.get("sequence") is not None:
        out.write(f"verification.sequence: {served['sequence']}\n")
    # A verdict merged from several pages says how many, on a line of its own:
    # « intact » over one page and over nine are not the same claim, and the
    # count is this client's, so it is not written as a member of the verdict.
    # One page needs no count, and the JSON envelope carries `pages` either way.
    if document["pages"] > 1:
        out.write(f"pages: {document['pages']}\n")
    out.write(f"local_check: {local['condition']}\n")
    # `version` belongs beside the other three: a chain the verifier could not
    # judge because it holds no reader for the recipe an entry declares names
    # that recipe here, and nowhere else in the prose. Without it the line
    # reads « unverifiable » and leaves the reader nothing to go and find.
    for member in ("sequence", "expected", "found", "version"):
        if local.get(member) is not None:
            out.write(f"local_check.{member}: {local[member]}\n")
    for gap in served["declared_gaps"]:
        out.write(f"gap: sequence {gap['sequence']} reason {gap['reason']} count {gap['count']}\n")
    for grade in served["grades"]:
        out.write(f"grade: {grade['connection_id']} {grade['grade']}\n")
    if served["condition"] != local["condition"]:
        out.write(
            f"finding: the plane says {served['condition']}, "
            f"the local check says {local['condition']}\n"
        )


def _online(arguments: argparse.Namespace, out: TextIO, err: TextIO, *, history: bool) -> int:
    connection = reads.open_connection(arguments, err)
    if isinstance(connection, int):
        return connection
    from_sequence = arguments.from_sequence
    render_answer = _write_history if history else _write_audit
    code = 0

    def walk() -> Result[Mapping[str, object]]:
        """Follow the continuations the daemon gives, and conclude once."""
        nonlocal from_sequence, code
        read_pages: list[Mapping[str, object]] = []
        entries: list[Mapping[str, object]] = []
        verdicts: list[Mapping[str, object]] = []
        while True:
            result = connection.read_evidence(arguments.scope, from_sequence, arguments.page_size)
            if not isinstance(result, Answered):
                return result
            # One depth rule, and it is read HERE, before a line of prose is
            # written: `pages.members` bounds this page at `PAGE_DEPTH_LIMIT`,
            # which is the render's own bound less the two levels this walk's
            # answer adds around a page. So a page it accepts is a page this
            # command can render, and a page it refuses is refused before
            # `_write_entries` has put anything on the caller's stdout —
            # which is what the half-render was.
            page_entries, served, next_from = pages.members(result.value, from_sequence)
            if history:
                read_pages.append(result.value)
                if not arguments.json:
                    _write_entries(page_entries, out)
            else:
                verdicts.append(served)
                entries.extend(
                    entry
                    for entry in page_entries
                    if arguments.to_sequence is None or entry["sequence"] <= arguments.to_sequence
                )
            if (
                next_from is None
                or (history and not arguments.all)
                or (
                    not history
                    and arguments.to_sequence is not None
                    and (
                        next_from > arguments.to_sequence
                        or (page_entries and page_entries[-1]["sequence"] >= arguments.to_sequence)
                    )
                )
            ):
                if history:
                    return Answered({"pages": read_pages}, CONTRACT_GENERATION)
                local = verify_chain(
                    entries,
                    scope=arguments.scope,
                    from_sequence=arguments.from_sequence,
                    to_sequence=arguments.to_sequence,
                )
                merged = _merged_verdict(verdicts)
                code = exit_for(local)
                if merged["condition"] != local.condition:
                    code = max(code, exit_codes.EXIT_CHECK_FAILED)
                return Answered(
                    {
                        "served": merged,
                        "local_check": local.to_document(),
                        "pages": len(verdicts),
                    },
                    CONTRACT_GENERATION,
                )
            from_sequence = next_from
            # An evidence read may close its HTTP connection. Reopening is
            # explicit and verifies the far end again, as rule C4 requires.
            connection.reconnect()

    try:
        result = reads.read(walk)
        if isinstance(result, Answered):
            rendered = reads.finish(result, arguments, connection, out, err, render_answer)
            # `finish` bounds the document it renders: one it could not render
            # is its own non-answer, not this read's local check.
            return code if rendered == 0 else rendered
        problem = replace(
            result.problem,
            message=f"stopped at from_sequence {from_sequence}: {result.problem.message}",
        )
        result = Refused(problem) if isinstance(result, Refused) else CouldNotAsk(problem)
        return reads.finish(result, arguments, connection, out, err, render_answer)
    finally:
        connection.close()


def _offline(arguments: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    verification = render.verification_document(None, None, False)
    try:
        bundle = json.loads(arguments.file.read_text(encoding="utf-8"))
        if reads.too_deep(bundle):
            raise ValueError(
                f"nested deeper than {reads.DOCUMENT_DEPTH_LIMIT} levels; "
                "not a bundle this client reads"
            )
        # What a bundle's CONTENT says about the chain is a verdict, never an
        # exception: a range carrying an entry of another scope, a recipe this
        # wheel holds no reader for, an instant outside the calendar are each
        # `unverifiable` at the sequence that could not be judged. So this
        # `except` is about the FILE and this reader — one that will not open,
        # will not parse, or nests past the bound — and it stays because a
        # traceback out of here would exit 1, the code for « denied ».
        local = verify_export(bundle)
    except (OSError, *reads.INPUT_ERRORS) as failure:
        return _could_not_check(arguments.file, failure, arguments.json, err)
    served = bundle.get("verification") if isinstance(bundle, Mapping) else None
    if arguments.json:
        render.write_json(
            render.envelope(
                CONTRACT_GENERATION,
                verification,
                result={"served": served, "local_check": local.to_document()},
            ),
            out,
        )
    else:
        _write_export_check(bundle, local, out)
    return exit_for(local)


def _list_entry(
    bundles: list[dict[str, object]],
    out: TextIO,
    name: str,
    *,
    as_json: bool,
    reason: str | None,
) -> None:
    """One listed entry that holds no verdict, said the same way in both modes.

    `reason` is what stopped the check, or `None` where there is nothing to
    check: « not a bundle » is a fact about the file, « could not check » is
    this client's own inability, and article 2 keeps them apart.
    """
    if reason is None:
        bundles.append({"file": name, "not_a_bundle": True})
    else:
        bundles.append({"file": name, "could_not_check": reason})
    if not as_json:
        out.write(f"{name} {'not a bundle' if reason is None else 'could not check'}\n")


def _could_not_check_entry(
    path: Path, failure: Exception, arguments: argparse.Namespace, err: TextIO, codes: set[int]
) -> str:
    """One entry of a listing could not be checked: 7 for the whole run.

    The reason goes to stderr in prose; in JSON it travels in the entry's own
    item, so stdout stays one parseable envelope however many entries fail.
    """
    codes.add(exit_codes.EXIT_COULD_NOT_CHECK)
    if not arguments.json:
        err.write(f"could not check: {path}: {failure}\n")
    return str(failure)


def _could_not_check(
    path: str | Path,
    failure: Exception,
    as_json: bool,
    err: TextIO,
    *,
    verification: Mapping[str, object] | None = None,
) -> int:
    """The check could not run at all; offline there is nothing verified to report."""
    message = f"could not check: {path}: {failure}"
    if as_json:
        problem = Problem(
            ProblemCode.ANSWER_UNREADABLE,
            message,
            problem_retryable(ProblemCode.ANSWER_UNREADABLE),
            CONTRACT_GENERATION,
        )
        render.write_json(
            render.envelope(
                CONTRACT_GENERATION,
                verification
                if verification is not None
                else render.verification_document(None, None, False),
                problem=problem.to_document(),
            ),
            err,
        )
    else:
        err.write(f"{message}\n")
    return exit_codes.EXIT_COULD_NOT_CHECK


def _write_export_check(bundle: object, local: ExportVerdict, out: TextIO) -> None:
    """The same offline check accompanies an audit and a newly saved export."""
    out.write(f"local_check: {local.overall}\n")
    if local.manifest_hash_recomputes is None:
        version = bundle.get("manifest_version") if isinstance(bundle, Mapping) else None
        manifest = f"unknown version {version if version is not None else render.NOT_STATED}"
    else:
        manifest = "recomputes" if local.manifest_hash_recomputes else "does not recompute"
    out.write(f"manifest: {manifest}\n")
    out.write(f"chain: {local.chain.condition if local.chain is not None else render.NOT_STATED}\n")
    if local.chain is not None:
        # Where the range stopped being what it claims, and — for a chain this
        # verifier could not judge — which recipe a reader has to go and find.
        # `unverifiable` without them is « something is wrong somewhere », which
        # is the shape of an absence stated as a fact (article 2).
        for member in ("sequence", "expected", "found", "version"):
            said = getattr(local.chain, member, None)
            if said is not None:
                out.write(f"chain.{member}: {said}\n")
    out.write(f"coverage: {local.coverage}\n")
    for issue in local.issues:
        out.write(f"issue: {issue}\n")
    served = bundle.get("verification") if isinstance(bundle, Mapping) else None
    condition = served.get("condition") if isinstance(served, Mapping) else None
    out.write(f"verification: {condition if condition is not None else render.NOT_STATED}\n")


COMMANDS: Final[dict[str, Callable[..., int]]] = {
    "history": _history,
    "audit": _audit,
    "export": _export,
    "exports": _exports,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sayfirst evidence", description="Read and check evidence."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        commands.add_parser(name, add_help=False)
    return parser


def main(
    argv: Sequence[str] | None = None, *, out: TextIO | None = None, err: TextIO | None = None
) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if forwarded and (command := COMMANDS.get(forwarded[0])) is not None:
        return command(forwarded[1:], out=out or sys.stdout, err=err or sys.stderr)
    build_parser().parse_args(forwarded)
    raise AssertionError("argparse accepted an evidence command that has no entry point")
