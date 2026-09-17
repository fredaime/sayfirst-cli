# SPDX-License-Identifier: Apache-2.0
"""What a pack may declare, refusal by refusal, each named by its own member.

Article 9 makes the manifest the whole interface between a person's choice of a
pack and the engine that installs it. So the interesting tests here are the
refusals: a manifest that is rejected without saying which member broke which
rule leaves the reader to guess, and a pack silently not installed is the
absence article 2 forbids rendering as a healthy state.

Every refusal asserts on the sentence as well as on the type, because the type
alone does not tell the person holding the manifest where to look.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contract_absence import contract_is_installed, skip_without_the_contract

from sayfirst_cli.instrument import manifest

HEADER: dict[str, str] = {
    "name": '"process-effects"',
    "classification": '"convenience"',
    "classified_on": "2026-09-14",
}
POINT: dict[str, str] = {
    "module": '"subprocess"',
    "attribute": '"Popen"',
    "capability": '"process.spawn"',
    "digest": '["args"]',
    "audit_event": '"subprocess.Popen"',
}


def text(*, drop: str | None = None, **overrides: str) -> str:
    """A manifest with one member replaced or removed, and everything else valid."""
    header, point = dict(HEADER), dict(POINT)
    for member, value in overrides.items():
        target = header if member in header else point
        target[member] = value
    header.pop(drop, None)
    point.pop(drop, None)
    lines = ["[pack]", *(f"{name} = {value}" for name, value in header.items())]
    if drop != "point":
        lines += ["", "[[point]]", *(f"{name} = {value}" for name, value in point.items())]
    return "\n".join(lines) + "\n"


def plant(root: Path, manifest_text: str | None = None, *, without: str | None = None) -> Path:
    """A pack directory, complete unless one of its three files is left out."""
    directory = root / "pack"
    directory.mkdir(exist_ok=True)
    for name in manifest.REQUIRED_FILES:
        if name == without:
            continue
        body = text() if manifest_text is None else manifest_text
        (directory / name).write_text(
            body if name == manifest.MANIFEST_FILE else "", encoding="utf-8"
        )
    return directory


def refusal(directory: Path) -> str:
    with pytest.raises(manifest.PackInvalid) as raised:
        manifest.read_pack(directory)
    return str(raised.value)


def test_a_valid_pack_reads_with_its_points(tmp_path: Path) -> None:
    """The whole of what the engine is given, read off the directory."""
    pack = manifest.read_pack(plant(tmp_path))
    assert pack.name == "process-effects"
    assert pack.classification == "convenience"
    assert (pack.classified_on.year, pack.classified_on.month) == (2026, 9)
    assert pack.directory == tmp_path / "pack"
    assert pack.execution_module == tmp_path / "pack" / manifest.EXECUTION_MODULE
    assert len(pack.points) == 1
    point = pack.points[0]
    assert (point.module, point.attribute) == ("subprocess", "Popen")
    assert point.capability == "process.spawn"
    assert point.digest == ("args",)
    assert point.audit_event == "subprocess.Popen"


def test_a_date_written_as_a_string_is_a_date_too(tmp_path: Path) -> None:
    """The manifest format may spell the date either way; both are ISO dates."""
    pack = manifest.read_pack(plant(tmp_path, text(classified_on='"2026-09-14"')))
    assert str(pack.classified_on) == "2026-09-14"


def test_two_points_both_arrive(tmp_path: Path) -> None:
    """A pack declares as many points as it likes, and the engine gets all of them."""
    second = text() + '\n[[point]]\nmodule = "shutil"\nattribute = "rmtree"\n'
    second += 'capability = "file.remove"\ndigest = ["path"]\naudit_event = "shutil.rmtree"\n'
    pack = manifest.read_pack(plant(tmp_path, second))
    assert [point.attribute for point in pack.points] == ["Popen", "rmtree"]


@pytest.mark.parametrize("missing", ["pack.toml", "interpose.py", "NOTE.md"])
def test_a_directory_that_is_not_all_three_files_is_not_a_pack(
    tmp_path: Path, missing: str
) -> None:
    """Article 9's shape: a manifest, a local execution module, a classification note."""
    assert missing in manifest.REQUIRED_FILES
    said = refusal(plant(tmp_path, without=missing))
    assert missing in said


def test_a_directory_that_is_not_there_is_refused_by_name(tmp_path: Path) -> None:
    """A path that does not exist is a misuse to report, never an empty pack."""
    said = refusal(tmp_path / "absent")
    assert manifest.MANIFEST_FILE in said


def test_a_manifest_that_does_not_parse_says_so(tmp_path: Path) -> None:
    said = refusal(plant(tmp_path, "[pack\nname = \n"))
    assert manifest.MANIFEST_FILE in said


def test_a_manifest_without_a_pack_table_is_refused(tmp_path: Path) -> None:
    said = refusal(plant(tmp_path, '[[point]]\nmodule = "subprocess"\n'))
    assert "[pack]" in said


@pytest.mark.parametrize("given", ['"Process"', '"-process"', '"process_effects"', '""', "7"])
def test_a_name_outside_the_published_shape_is_refused(tmp_path: Path, given: str) -> None:
    """A pack name is lower case, digits and hyphens: one spelling, not several."""
    said = refusal(plant(tmp_path, text(name=given)))
    assert "name" in said


def test_a_pack_with_no_name_is_refused(tmp_path: Path) -> None:
    assert "name" in refusal(plant(tmp_path, text(drop="name")))


@pytest.mark.parametrize("given", ['"framework"', '"Convenience"', '""', "true"])
def test_a_classification_this_format_does_not_admit_is_refused(tmp_path: Path, given: str) -> None:
    """Article 9 ships convenience packs; anything else is a pack this is not."""
    said = refusal(plant(tmp_path, text(classification=given)))
    assert "classification" in said


def test_a_pack_with_no_classification_is_refused(tmp_path: Path) -> None:
    assert "classification" in refusal(plant(tmp_path, text(drop="classification")))


@pytest.mark.parametrize("given", ['"not-a-date"', '"14/09/2026"', '""', "2026", "true"])
def test_a_classification_date_that_is_not_one_is_refused(tmp_path: Path, given: str) -> None:
    """The classification carries the date it was made, so it can be re-examined."""
    said = refusal(plant(tmp_path, text(classified_on=given)))
    assert "classified_on" in said


def test_a_pack_with_no_classification_date_is_refused(tmp_path: Path) -> None:
    assert "classified_on" in refusal(plant(tmp_path, text(drop="classified_on")))


def test_a_pack_that_declares_no_point_installs_nothing_and_is_refused(tmp_path: Path) -> None:
    """An engine that installed nothing must not report that it installed a pack."""
    said = refusal(plant(tmp_path, text(drop="point")))
    assert "[[point]]" in said


def test_a_point_member_that_is_not_a_list_of_tables_is_refused(tmp_path: Path) -> None:
    """A member spelled as a value rather than as a table array declares no point."""
    said = refusal(plant(tmp_path, "point = 1\n\n" + text(drop="point")))
    assert "[[point]]" in said


@pytest.mark.parametrize("given", ['"sub process"', '"9lives"', '"a..b"', '""', '"class"', "7"])
def test_a_module_that_is_not_a_dotted_identifier_is_refused(tmp_path: Path, given: str) -> None:
    said = refusal(plant(tmp_path, text(module=given)))
    assert "module" in said


def test_a_point_with_no_module_is_refused(tmp_path: Path) -> None:
    assert "module" in refusal(plant(tmp_path, text(drop="module")))


@pytest.mark.parametrize("given", ['"Po pen"', '"a.b"', '""', '"import"', "[]"])
def test_an_attribute_that_is_not_an_identifier_is_refused(tmp_path: Path, given: str) -> None:
    said = refusal(plant(tmp_path, text(attribute=given)))
    assert "attribute" in said


def test_a_point_with_no_attribute_is_refused(tmp_path: Path) -> None:
    assert "attribute" in refusal(plant(tmp_path, text(drop="attribute")))


@pytest.mark.parametrize(
    "given",
    [
        '"Process.Spawn"',
        '"process.."',
        '""',
        "1",
        # The defect this rule was rewritten for: an underscore. The client's
        # own copy of the shape admitted one, and a pack this distribution
        # ships declared a capability the plane refuses as malformed.
        '"net_egress"',
        '"process.sub_command"',
        # Past the length the schema states, which the copy never bounded.
        '"' + "a" * 200 + '"',
    ],
)
def test_a_capability_outside_the_published_shape_is_refused(tmp_path: Path, given: str) -> None:
    """The shape is the control plane's, read off its own ask-request schema.

    The refusal quotes the schema's pattern rather than paraphrasing it, so a
    pack author checks their spelling against the same text the daemon will.
    """
    said = refusal(plant(tmp_path, text(capability=given)))
    assert "capability" in said
    assert manifest.ASK_REQUEST_SCHEMA in said
    assert manifest.capability_rule().stated in said


def test_the_shape_this_client_applies_is_the_schemas_own_pattern() -> None:
    """Read, never transcribed: the rule and the schema are the same object.

    A regular expression copied into the client is a second rule that agrees on
    the day it is written and drifts afterwards — which is what happened, in two
    directions at once. So the rule is asserted to BE the schema's, through the
    contract's own artefact loader, rather than asserted to look like it.
    """
    from sayfirst_contract.artifacts import domain_schema

    published = domain_schema(manifest.ASK_REQUEST_SCHEMA)["properties"]
    member = published[manifest.CAPABILITY_MEMBER]
    rule = manifest.capability_rule()
    assert rule.stated == member["pattern"]
    assert rule.shortest == member["minLength"]
    assert rule.longest == member["maxLength"]
    # And the pattern really is the narrower one: no underscore, no capital.
    assert rule.shape.fullmatch("net_egress") is None
    assert rule.shape.fullmatch("Net.Egress") is None
    assert rule.shape.fullmatch("net.egress") is not None


def test_a_single_word_the_schema_admits_is_no_longer_this_clients_to_refuse(
    tmp_path: Path,
) -> None:
    """« At least two segments » was the client's own rule, and it is gone.

    The schema's pattern admits a single bare word, so a pack declaring one asks
    a question the plane will accept — and a client that refused it would be
    inventing a rule the contract does not state, which is the whole of what
    this change removed. What still refuses a bare word is the other rule, when
    the word is the library's own name: the test below.
    """
    pack = manifest.read_pack(plant(tmp_path, text(capability='"spawn"')))
    assert pack.points[0].capability == "spawn"


def test_a_single_word_that_is_the_librarys_own_name_is_still_refused(tmp_path: Path) -> None:
    """The two rules are independent, and this is why both are needed.

    `subprocess` is a spelling the schema admits — one lower-case word — and it
    is the module the point is declared on, so the client's own rule refuses it.
    Dropping the segment count did not open this door; it was the segment
    comparison that closed it, and it stays closed.
    """
    said = refusal(plant(tmp_path, text(capability='"subprocess"')))
    assert "segment 'subprocess' is one" in said
    assert "article 4" in said


def test_a_point_with_no_capability_is_refused(tmp_path: Path) -> None:
    assert "capability" in refusal(plant(tmp_path, text(drop="capability")))


def test_a_capability_that_is_the_module_it_wraps_is_refused(tmp_path: Path) -> None:
    """Article 4: a capability is a kind of effect, never a library name."""
    said = refusal(plant(tmp_path, text(module='"urllib.request"', capability='"urllib.request"')))
    assert "capability" in said
    assert "article 4" in said


def test_a_capability_that_is_a_prefix_of_the_module_it_wraps_is_refused(tmp_path: Path) -> None:
    """The same rule one segment up, which is where it is easiest to slip through."""
    said = refusal(
        plant(tmp_path, text(module='"urllib.request.thing"', capability='"urllib.request"'))
    )
    assert "article 4" in said


@pytest.mark.parametrize("given", ["[]", '"args"', '[""]', '["a b"]', "[1]", '["a", 2]'])
def test_a_digest_that_is_not_a_non_empty_list_of_identifiers_is_refused(
    tmp_path: Path, given: str
) -> None:
    """Article 11: the point says which call arguments form the digest, by name."""
    said = refusal(plant(tmp_path, text(digest=given)))
    assert "digest" in said


def test_a_point_with_no_digest_is_refused(tmp_path: Path) -> None:
    assert "digest" in refusal(plant(tmp_path, text(drop="digest")))


@pytest.mark.parametrize("given", ['""', "7", "[]"])
def test_an_audit_event_that_is_not_a_sentence_is_refused(tmp_path: Path, given: str) -> None:
    said = refusal(plant(tmp_path, text(audit_event=given)))
    assert "audit_event" in said


def test_a_point_with_no_audit_event_is_refused(tmp_path: Path) -> None:
    assert "audit_event" in refusal(plant(tmp_path, text(drop="audit_event")))


def test_the_pack_and_its_points_are_frozen(tmp_path: Path) -> None:
    """The engine is handed a declaration, not a mutable working copy of one."""
    pack = manifest.read_pack(plant(tmp_path))
    with pytest.raises(AttributeError):
        pack.name = "renamed"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        pack.points[0].capability = "other.effect"  # type: ignore[misc]


# --- A capability is never a library name, segment by segment -------------------


@pytest.mark.parametrize(
    ("module", "attribute", "capability", "segment"),
    [
        ('"subprocess"', '"Popen"', '"subprocess.run"', "subprocess"),
        ('"subprocess"', '"run"', '"process.run"', "run"),
        ('"requests"', '"Session"', '"requests.session"', "requests"),
        ('"urllib.request"', '"urlopen"', '"urllib.get"', "urllib"),
        ('"urllib.request"', '"urlopen"', '"http.request"', "request"),
        ('"urllib.request"', '"urlopen"', '"net.urlopen"', "urlopen"),
        ('"sqlite3"', '"connect"', '"sqlite3.connect"', "sqlite3"),
        ('"shutil"', '"rmtree"', '"file.rmtree"', "rmtree"),
        # The case-folding half of the rule. Every one of these was
        # measured as ACCEPTED while the comparison kept the case: a capability
        # cannot carry an upper-case letter, so the rule could only ever match
        # the spellings its own shape had already refused, and the first shipped
        # pack's attribute is CamelCase.
        ('"subprocess"', '"Popen"', '"process.popen"', "popen"),
        ('"subprocess"', '"Popen"', '"popen.spawn"', "popen"),
        ('"SomeLib"', '"Thing"', '"somelib.thing"', "somelib"),
        ('"SomeLib"', '"Thing"', '"effect.thing"', "thing"),
    ],
)
def test_a_capability_that_borrows_a_name_from_the_point_is_refused(
    tmp_path: Path, module: str, attribute: str, capability: str, segment: str
) -> None:
    """Every example the review measured as wrongly ACCEPTED, now refused by name."""
    said = refusal(plant(tmp_path, text(module=module, attribute=attribute, capability=capability)))
    assert "capability" in said
    assert f"segment {segment!r} is one" in said
    assert "article 4" in said


@pytest.mark.parametrize(
    ("module", "attribute", "capability"),
    [
        ('"subprocess"', '"Popen"', '"process.spawn"'),
        ('"urllib.request"', '"urlopen"', '"net.egress"'),
        ('"sqlite3"', '"connect"', '"data.store"'),
        ('"shutil"', '"rmtree"', '"file.remove"'),
        ('"SomeLib"', '"Thing"', '"mail.send"'),
    ],
)
def test_a_capability_that_names_the_effect_is_accepted(
    tmp_path: Path, module: str, attribute: str, capability: str
) -> None:
    """The other side of the rule: naming the effect is what a pack author does.

    The rule folds case now, so what is left for a pack author is to say what
    HAPPENS: a capability that differs from the attribute only in case is the
    library name again and is refused above, and none of these borrows a
    segment from either the module path or the attribute in any casing.
    """
    pack = manifest.read_pack(
        plant(tmp_path, text(module=module, attribute=attribute, capability=capability))
    )
    assert pack.points[0].capability == capability.strip('"')


def test_the_old_whole_spelling_rule_still_refuses_what_it_refused(tmp_path: Path) -> None:
    """A widening that stopped catching what the narrow rule caught would be a loss."""
    said = refusal(plant(tmp_path, text(module='"urllib.request"', capability='"urllib.request"')))
    assert "article 4" in said
    said = refusal(
        plant(tmp_path, text(module='"urllib.request.thing"', capability='"urllib.request"'))
    )
    assert "article 4" in said


def test_extra_entries_beside_the_three_files_are_ignored(tmp_path: Path, request) -> None:
    """The reader requires the three files and ignores the rest — a note, a helper,
    a bytecode cache, a nested directory — as the format description says.

    The pack is planted by `governed_programs`, which needs the contract, while
    the rest of this module does not — so the import is inside the test and the
    absence rule cannot see it at collection. Without the stand-down below this
    was the one test in a reduced run that FAILED for the contract's absence
    instead of being counted, which is article 2's rule inverted: the absence
    rendered as a defect.
    """
    if not contract_is_installed():
        skip_without_the_contract(request, "the pack is planted by `governed_programs`")
    from governed_programs import plant_pack

    directory = plant_pack(
        tmp_path,
        name="roomy",
        module="example_mod",
        attribute="effect",
        capability="example.action",
    )
    (directory / "README.md").write_text("about this pack\n", encoding="utf-8")
    (directory / "helper.py").write_text("HELPER = 1\n", encoding="utf-8")
    (directory / "__pycache__").mkdir()
    (directory / "__pycache__" / "interpose.cpython-313.pyc").write_bytes(b"\x00")
    (directory / "nested").mkdir()
    pack = manifest.read_pack(directory)
    assert pack.name == "roomy"
    assert [point.attribute for point in pack.points] == ["effect"]


# --- A deep manifest is a refusal, not a traceback ------------------------------

#: A nesting deeper than any parser descends, and the shape an ordinary mistake
#: takes: a generated or truncated document, not an attack. 3000 is far past
#: the interpreter's own limit at any stack depth these tests run at.
DEEP = "x = " + "[" * 3000 + "]" * 3000 + "\n"


def test_a_manifest_nested_deeper_than_this_reader_parses_is_refused(tmp_path: Path) -> None:
    """`RecursionError` beside the other three, and for the same reason.

    Left to the interpreter it is a traceback and exit 1 — this client's
    published code for « the control plane answered deny » — published for a
    file the invocation merely NAMED, with no question ever put (articles 1 and
    2). The refusal names the member and the rule, like every other.
    """
    said = refusal(plant(tmp_path, DEEP))
    assert manifest.MANIFEST_FILE in said
    assert "nests deeper than this reader parses" in said
