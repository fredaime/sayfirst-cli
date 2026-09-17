# SPDX-License-Identifier: Apache-2.0
"""Every pack this distribution carries is complete, read the way the client reads it.

Every assertion below goes through the client's own reader,
`sayfirst_cli.packs_cmd.shipped_packs`, rather than a path built off this
file's location — so what is proven here is that the reader and the packs agree,
for whatever install the tests are running against.

**Which is not a packaging proof, and this file does not claim to be one.**
`importlib.resources` changes how a path is computed, not where the bytes come
from: under the editable install the gate uses, `shipped_packs()` resolves to
`src/sayfirst_cli/packs`, the source tree. A missing package-data declaration
would pass every test here. The rule that the *built wheel* carries each pack's
three files is measured by `scripts/check_dependency_closure.py`, which
installs the wheel into an empty environment and asks it this same question
there — the gate's closure step, which prints what it found. This file proves
the reader; that step proves the packaging. Neither reads as the other.

The no-registry statement in `docs/PACKS.md` carries its own re-examination
date, read back here as the date the statement itself names — not the wheel's
concern, so read from the repository file directly (article 9's own words:
"past that date the packaging test fails until it is renewed or replaced").
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from sayfirst_cli import exit_codes, packs_cmd
from sayfirst_cli.instrument import manifest

REPOSITORY = Path(__file__).resolve().parents[1]
PACKS_DOC = REPOSITORY / "docs" / "PACKS.md"

#: `statement-reexamined-by: YYYY-MM-DD`, on its own line, in `docs/PACKS.md`.
_REEXAMINED = re.compile(r"statement-reexamined-by:\s*(\d{4}-\d{2}-\d{2})")

#: One row of the shipped-packs table in `docs/PACKS.md`: the name in
#: backticks, the capability, and the date the pack was classified.
_TABLE_ROW = re.compile(
    r"^\|\s*`([a-z][a-z0-9-]*)`\s*\|\s*`([a-z][a-z0-9.]*)`\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|"
)


def test_the_walk_found_at_least_one_pack() -> None:
    """Anti-vacuity, held apart from the assertions below: a walk over nothing
    must not read as every pack below having passed."""
    assert len(packs_cmd.shipped_packs()) >= 1, "no pack found under the installed package"


def test_the_walk_found_exactly_the_three_packs_this_distribution_ships() -> None:
    """Article 9 names three convenience packs; this is the day the third shipped.

    A stronger anti-vacuity than the one above, and a different failure mode
    than `test_the_published_table_lists_exactly_the_packs_that_ship`: that test
    holds the document against whatever ships, however many that is; this one
    holds the count and the names against the number article 9 actually names,
    so a fourth pack arriving unannounced, or one of the three going missing,
    fails here even if `docs/PACKS.md` was edited to agree with it.
    """
    shipped = packs_cmd.shipped_packs()
    names = sorted(manifest.read_pack(directory).name for directory in shipped)
    assert len(shipped) == 3, shipped
    assert names == ["database", "http-client", "subprocess"]


def test_every_shipped_pack_is_complete_and_readable_as_installed() -> None:
    shipped = packs_cmd.shipped_packs()
    for directory in shipped:
        for required in manifest.REQUIRED_FILES:
            assert (directory / required).is_file(), f"{directory} is missing {required}"
        pack = manifest.read_pack(directory)
        assert pack.name
        assert pack.points


def test_every_shipped_notes_classification_and_carries_a_date() -> None:
    for directory in packs_cmd.shipped_packs():
        note = (directory / manifest.CLASSIFICATION_NOTE).read_text(encoding="utf-8")
        assert "convenience" in note, directory
        # A justification sentence, not just the word: article 9's own test is
        # that a competent engineer could rebuild the pack from public
        # documentation, and that sentence has to actually be there.
        assert len(note.split()) > 15, (directory, note)
        assert re.search(r"\d{4}-\d{2}-\d{2}", note), (directory, note)


def _documented_packs() -> dict[str, tuple[str, str]]:
    """The shipped-packs table of `docs/PACKS.md`, as name → (capability, date).

    The capability column joined the reading after a shipped pack's capability
    moved and the row did not: the column was matched and thrown away, so the
    document could name a capability no pack declared and no guard would see it.
    """
    rows: dict[str, tuple[str, str]] = {}
    table = False
    for line in PACKS_DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith("|"):
            if not table:
                table = True  # the header row
                continue
            if line.replace("|", "").replace("-", "").strip() == "":
                continue  # the separator row
            matched = _TABLE_ROW.match(line)
            # A row the pattern does not recognise is still a claim about a
            # pack; it fails here rather than being silently left out.
            assert matched is not None, f"a table row is not in the documented shape: {line}"
            rows[matched.group(1)] = (matched.group(2), matched.group(3))
        elif table and line.strip() == "":
            table = False
    return rows


def test_the_published_table_lists_exactly_the_packs_that_ship() -> None:
    """The document's claim about what this distribution governs, held against
    what it carries — both ways round.

    A hand-maintained table that lost a row would say the client governs less
    than it does; one that kept a row for a pack that no longer ships would say
    the opposite. Both pass every gate that never reads the table, which is
    what this repository's guards exist to refuse.
    """
    shipped = {}
    for directory in packs_cmd.shipped_packs():
        pack = manifest.read_pack(directory)
        capabilities = dict.fromkeys(point.capability for point in pack.points)
        assert len(capabilities) == 1, (pack.name, sorted(capabilities))
        shipped[pack.name] = (next(iter(capabilities)), pack.classified_on.isoformat())
    assert shipped, "no pack found under the installed package"
    assert _documented_packs() == shipped


def _the_reexamination_date() -> date:
    text = PACKS_DOC.read_text(encoding="utf-8")
    matched = _REEXAMINED.search(text)
    assert matched, f"{PACKS_DOC} carries no statement-reexamined-by: line"
    return date.fromisoformat(matched.group(1))


def no_registry_statement_is_current(*, today: date) -> bool:
    """The no-registry statement is still current, read against an injected clock.

    A function rather than a bare assertion, so the proof below can call it
    with a date that has not arrived yet and require the SAME rule to say no.
    """
    return today < _the_reexamination_date()


def test_the_no_registry_statement_is_current() -> None:
    """The gate's own run of this rule: the docs file is read from the
    repository (never the wheel — packaging carries no documentation), and
    today's date has not reached the re-examination date."""
    assert PACKS_DOC.is_file(), f"{PACKS_DOC} is read from the repository, not the wheel"
    assert no_registry_statement_is_current(today=date.today())


def test_the_rule_fails_once_its_own_reexamination_date_has_come() -> None:
    """The self-proof article 9 asks for: fixed to 2027-03-14, the rule says no.

    The day before is `- timedelta(days=1)` and not `replace(day=day - 1)`:
    the second raises `ValueError` on any first-of-month deadline, so the guard
    that has to survive its own renewal would have broken during it.
    """
    deadline = _the_reexamination_date()
    assert deadline == date(2027, 3, 14)
    assert no_registry_statement_is_current(today=deadline - timedelta(days=1))
    assert not no_registry_statement_is_current(today=deadline)


def test_the_day_before_is_computed_the_way_a_renewal_will_survive() -> None:
    """The arithmetic itself, on the date that would have broken it."""
    assert date(2028, 1, 1) - timedelta(days=1) == date(2027, 12, 31)


def test_a_table_row_the_pattern_does_not_recognise_fails_the_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`| sqlite | … |` without backticks is a claim too; it must not slip past."""
    doctored = tmp_path / "PACKS.md"
    # The bogus row goes INSIDE the table, right before the real one.
    doctored.write_text(
        PACKS_DOC.read_text(encoding="utf-8").replace(
            "| `subprocess` |",
            "| sqlite | `db.query` | 2026-09-15 | a row without backticks |\n| `subprocess` |",
            1,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "PACKS_DOC", doctored)
    with pytest.raises(AssertionError, match="not in the documented shape"):
        _documented_packs()


# --- the document's two claims about rules that live in code -------------------

#: Every exit code `sayfirst instrument verify` answers with, by the name
#: `exit_codes.CODES` gives each rather than by the number: a renumber there
#: fails here instead of drifting quietly from the document.
#:
#: `misuse` is in it because the verb really does answer 64 — for an invocation
#: the harness refused before it began, and for a profile this command refuses
#: before a second interpreter is started. It was absent while the document was
#: silent about it, and the guard below only ever caught a STALE number, never a
#: missing one, so the docstring's second half was not earned. Both directions
#: are held now.
VERIFY_CODES: tuple[str, ...] = (
    "allow",
    "could_not_ask",
    "check_failed",
    "could_not_check",
    "misuse",
)

#: The one `sayfirst packs list` answers with beyond a clean listing.
LISTING_CODE = "misuse"


def _section(title: str) -> str:
    """One `##` section of the document, by its heading."""
    text = PACKS_DOC.read_text(encoding="utf-8")
    start = text.index(f"## {title}")
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def _a_pack_declaring(root: Path, *, module: str, attribute: str, capability: str) -> Path:
    """A complete pack directory, whose only interesting member is the capability."""
    directory = root / capability.replace(".", "-")
    directory.mkdir(parents=True)
    (directory / manifest.MANIFEST_FILE).write_text(
        "[pack]\n"
        'name = "documented"\n'
        'classification = "convenience"\n'
        "classified_on = 2026-09-15\n"
        "\n"
        "[[point]]\n"
        f'module = "{module}"\n'
        f'attribute = "{attribute}"\n'
        f'capability = "{capability}"\n'
        'digest = ["first"]\n'
        f'audit_event = "{module}.{attribute}"\n',
        encoding="utf-8",
    )
    (directory / manifest.EXECUTION_MODULE).write_text(
        "def wrap(original, capability, boundary):\n    return original\n", encoding="utf-8"
    )
    (directory / manifest.CLASSIFICATION_NOTE).write_text(
        "A convenience pack written for one test: a competent engineer would rebuild it in a "
        "day from public documentation, which is article 9's own test. Classified 2026-09-15.\n",
        encoding="utf-8",
    )
    return directory


#: The document's own worked examples of the capability rule, refused and
#: accepted. Asserted against the reader rather than matched as prose: a
#: document that stated a rule the code does not enforce is the failure this is
#: for, and string matching cannot see it.
REFUSED = (("subprocess", "Popen", "process.popen"), ("sqlite3", "connect", "database.connect"))
ACCEPTED = (("subprocess", "Popen", "process.spawn"), ("sqlite3", "connect", "database.open"))


def test_the_document_states_the_capability_rule_and_the_codes_the_command_uses() -> None:
    """Both halves of « the document says only what the code does ».

    The rule: the document's worked examples are put through `manifest`'s own
    reader, so a document that described a rule the reader does not enforce
    fails here. The codes: every number the `Verifying` section names is one
    this client publishes, and every code `verify` answers with is named — so
    neither a stale number nor an undocumented one survives.
    """
    document = PACKS_DOC.read_text(encoding="utf-8")
    assert "segment of a capability" in document
    assert manifest.ASK_REQUEST_SCHEMA in document
    assert "case folded" in document
    assert "manifest.py" in document

    verifying = _section("Verifying")
    named = {int(found) for found in re.findall(r"`(\d+)`", verifying)}
    published = set(exit_codes.CODES.values())
    assert named <= published, sorted(named - published)
    for name in VERIFY_CODES:
        assert exit_codes.CODES[name] in named, name
    listing = _section("The packs this distribution ships")
    assert exit_codes.CODES[LISTING_CODE] in {
        int(found) for found in re.findall(r"`(\d+)`", listing)
    }


def test_the_capability_rule_the_document_states_is_the_rule_the_reader_enforces(
    tmp_path: Path,
) -> None:
    """The document's examples, run through `manifest.read_pack` both ways round."""
    for module, attribute, capability in REFUSED:
        pack = _a_pack_declaring(
            tmp_path / "refused", module=module, attribute=attribute, capability=capability
        )
        with pytest.raises(manifest.PackInvalid, match="never a library name"):
            manifest.read_pack(pack)
    for module, attribute, capability in ACCEPTED:
        pack = _a_pack_declaring(
            tmp_path / "accepted", module=module, attribute=attribute, capability=capability
        )
        assert manifest.read_pack(pack).points[0].capability == capability


def _borrowed_segment(capability: str, module: str, attribute: str) -> str | None:
    """A segment the capability takes from the point, read independently of the client.

    Recomputed here rather than asked of `manifest`'s own private helper: a test
    that calls the code under test to decide what the answer should be proves
    the code agrees with itself.
    """
    from_the_point = {segment.casefold() for segment in (*module.split("."), attribute)}
    return next(
        (segment for segment in capability.split(".") if segment.casefold() in from_the_point),
        None,
    )


def test_every_shipped_capability_is_one_the_control_plane_admits() -> None:
    """The first of the two rules, over what actually ships.

    The rule is the control plane's and is read off its published ask-request
    schema, so this asserts against the schema rather than against a spelling
    written here — a pack whose capability the daemon would refuse as malformed
    is a pack that governs nothing while appearing to, and the client shipped
    one until this rule was read rather than copied.
    """
    from sayfirst_contract.artifacts import domain_schema

    member = domain_schema(manifest.ASK_REQUEST_SCHEMA)["properties"][manifest.CAPABILITY_MEMBER]
    shape = re.compile(member["pattern"])
    shipped = packs_cmd.shipped_packs()
    assert len(shipped) >= 3, shipped
    for directory in shipped:
        pack = manifest.read_pack(directory)
        assert pack.points, directory
        for point in pack.points:
            assert shape.fullmatch(point.capability) is not None, (pack.name, point.capability)
            assert member["minLength"] <= len(point.capability) <= member["maxLength"]


def test_no_shipped_capability_borrows_a_name_from_the_point_it_governs() -> None:
    """The second rule, over what actually ships, and the reason both are needed.

    The schema's shape would admit a capability spelled exactly as the library
    it wraps; this is what refuses it. Asserted over every point of every
    shipped pack, and with the anti-vacuity that the comparison really can fire.
    """
    shipped = packs_cmd.shipped_packs()
    assert len(shipped) >= 3, shipped
    for directory in shipped:
        pack = manifest.read_pack(directory)
        for point in pack.points:
            borrowed = _borrowed_segment(point.capability, point.module, point.attribute)
            assert borrowed is None, (pack.name, point.capability, borrowed)
            # Anti-vacuity: the same comparison, given the module's own name,
            # answers. A reading that could never fire would pass the loop above
            # over any capability at all.
            assert _borrowed_segment(point.module, point.module, point.attribute) is not None
