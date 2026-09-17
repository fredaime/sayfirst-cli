# SPDX-License-Identifier: Apache-2.0
"""What a pack declares, read strictly, because the engine trusts nothing else.

A pack is code a person chose to run and named on the command line (article 9).
Its manifest is the whole interface between that choice and the engine: the
engine special-cases nothing and carries no vocabulary of its own, so every
rule about what may be declared is enforced here, once, before anything is
wrapped.

What a pack directory must carry is the three files named below, and what it
may carry besides them is anything: the reader requires the three and ignores
the rest. Not laxity — a directory Python has imported anything from holds a
bytecode cache nobody put there, and a reader that refused a pack over one
would refuse for a reason that has nothing to do with what the pack declares.

Every refusal names the member and the rule it broke. A manifest rejected
without saying which line is wrong leaves the reader to guess, and a pack
silently not installed is the absence article 2 forbids rendering as a healthy
state — the program would run ungoverned and nothing would have said so.

**A capability is judged by two rules, and only one of them is this client's.**

The first is the contract's: what a capability may be SPELLED like is published
in the ask-request schema, because that is the document the daemon validates a
question against, and this file reads the rule off it through the contract's own
artefact loader rather than keeping a copy. A copy was kept here once, and it
was wider than the original in two ways at once — it admitted an underscore and
it demanded two segments — so a pack this distribution shipped declared a
capability the plane would refuse as malformed, and nothing in this repository
could see it: the pack read, the engine installed it, and the ask was rejected
inside somebody's program. A rule the contract owns is read, never restated; if
the schema stops carrying it, that is said as a refusal naming the schema
rather than guessed at.

The second is this client's own, and it is about naming rather than spelling: a
capability is a kind of effect and never a library name (article 4), so no
segment of a capability may be a segment of the module path it is declared on,
nor the attribute it wraps, compared with the case folded on both sides. « The
effect is whatever this library is called » cannot be declared at all. That rule
used to compare whole dotted spellings, and the review that found it said why
that could never work: a capability spelled as a one-segment module's own name,
or as the one attribute it wraps, was accepted whenever the module was a single
segment. It is segments now, and a capability that borrows the *last* segment of
a deeper module path is refused too — a pack author who wants that effect names
what HAPPENS (`parcel.dispatch` over a courier library's own name), which is the
rule working rather than the rule being awkward.

The two are independent and both are needed: the contract's shape admits a
single bare word, and the client's rule is what stops that word being the
library's own name.

(No paragraph in this FILE — not this one, not a docstring further down —
names a module or an attribute a shipped pack declares, on purpose:
`tests/test_engine_is_agnostic.py` binds this file too, and scans prose for
both halves of a shipped pack's vocabulary, because an illustration that
happened to spell out a pack's own attribute would be exactly the special case
article 4 forbids, arriving as prose instead of as code. Every example here is
invented, and the rule is the file's rather than the paragraph's — that
distinction is not pedantry: it was first written as a paragraph's promise, and
a review then found a real attribute spelled out eight screens below it.)
"""

from __future__ import annotations

import keyword
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Final, NamedTuple

from sayfirst_contract.artifacts import domain_schema

#: The file that declares the pack.
MANIFEST_FILE: Final[str] = "pack.toml"

#: The local execution module, which produces the wrapper for a point.
EXECUTION_MODULE: Final[str] = "interpose.py"

#: The classification note: what kind of pack this is, why, and from when.
CLASSIFICATION_NOTE: Final[str] = "NOTE.md"

#: What a pack directory must carry (article 9). A directory missing any of the
#: three is not a pack, and the engine installs nothing from it. A directory
#: carrying more than the three still is one: `read_pack` requires these and
#: reads nothing else in the directory.
REQUIRED_FILES: Final[tuple[str, ...]] = (MANIFEST_FILE, EXECUTION_MODULE, CLASSIFICATION_NOTE)

#: The one classification this format admits. Article 9 ships convenience packs
#: — the ones a competent engineer would rebuild in a day — and nothing else.
CONVENIENCE: Final[str] = "convenience"

#: The members a pack declares about itself, and the members a point declares.
#: Read through a table seeded with `None`, so that « declared as the wrong
#: thing » and « not declared at all » take the same path to the same refusal —
#: two paths to one refusal is how one of them comes to be forgotten.
PACK_MEMBERS: Final[tuple[str, ...]] = ("name", "classification", "classified_on")
POINT_MEMBERS: Final[tuple[str, ...]] = (
    "module",
    "attribute",
    "capability",
    "digest",
    "audit_event",
)

_PACK_NAME: Final = re.compile(r"^[a-z][a-z0-9-]*$")

#: The published schema whose `capability` member is the rule a capability is
#: judged by. Named here because it is the document the DAEMON validates a
#: question against: a spelling it refuses is a question that cannot be asked,
#: whatever this client thinks of it.
ASK_REQUEST_SCHEMA: Final[str] = "decision-ask-request"

#: The member of that schema this file reads.
CAPABILITY_MEMBER: Final[str] = "capability"


class CapabilityRule(NamedTuple):
    """The contract's rule for a capability spelling, as its own schema states it.

    `stated` is the pattern's own source text, carried so that a refusal can
    quote the rule rather than paraphrase it: a reader told « lower case,
    dotted » has to trust the paraphrase, while a reader shown the pattern can
    check their spelling against the same thing the daemon will.
    """

    shape: re.Pattern[str]
    stated: str
    shortest: int
    longest: int


@cache
def capability_rule() -> CapabilityRule:
    """The rule a capability must satisfy, read off the contract's published schema.

    Read through the contract's own artefact loader, once per process, and never
    transcribed: a regular expression copied into this file is a second rule
    that agrees with the first on the day it is written and drifts afterwards —
    which is exactly what happened. The copy admitted an underscore and demanded
    two segments, so a pack this distribution ships declared a capability the
    plane refuses as malformed, and nothing here could see it.

    A schema carrying no pattern for the member is a contract this client cannot
    read a capability against, and it says so as a `PackInvalid` naming the
    schema and the member; a contract distribution that ships no such schema at
    all is outside what this reader guards and escapes as itself. That is the
    honest ending for the member: no pack is installed, and
    the code the caller sees already means « the invocation was wrong, or
    something it named cannot be read » — where an escaping exception would
    reach a shell as exit 1, this client's code for « denied ».
    """
    properties = domain_schema(ASK_REQUEST_SCHEMA).get("properties")
    member = properties.get(CAPABILITY_MEMBER) if isinstance(properties, dict) else None
    stated = member.get("pattern") if isinstance(member, dict) else None
    if not isinstance(member, dict) or not isinstance(stated, str):
        raise PackInvalid(
            f"the published {ASK_REQUEST_SCHEMA} schema states no pattern for its "
            f"{CAPABILITY_MEMBER} member, so this client cannot read a capability "
            f"against the rule the control plane publishes"
        )
    shortest = member.get("minLength")
    longest = member.get("maxLength")
    return CapabilityRule(
        re.compile(stated),
        stated,
        shortest if isinstance(shortest, int) else 1,
        longest if isinstance(longest, int) else 0,
    )


class PackInvalid(ValueError):
    """A manifest that will not be installed, carrying the member and the rule."""


@dataclass(frozen=True)
class Point:
    """One interposition: what to wrap, and as which kind of effect."""

    module: str
    attribute: str
    capability: str
    digest: tuple[str, ...]
    audit_event: str


@dataclass(frozen=True)
class Pack:
    """A pack as read off its own directory, and the directory it was read from."""

    name: str
    classification: str
    classified_on: date
    points: tuple[Point, ...]
    directory: Path

    @property
    def execution_module(self) -> Path:
        """Where the wrapper comes from. The engine loads it by path, never by name."""
        return self.directory / EXECUTION_MODULE


def read_pack(path: Path) -> Pack:
    """Read one pack directory, or refuse it by naming the member and the rule.

    The three required files are required; the directory's other entries, if it
    has any, are not read and not refused.
    """
    for required in REQUIRED_FILES:
        if not (path / required).is_file():
            raise PackInvalid(
                f"{required} is missing from {path}: a pack is a manifest, a local "
                f"execution module and a classification note, and a directory that is "
                f"not all three declares nothing this engine will install"
            )
    try:
        document = tomllib.loads((path / MANIFEST_FILE).read_text(encoding="utf-8"))
    except RecursionError as too_deep:
        # A document nested deeper than this reader's parser descends. Caught
        # beside the three below rather than left to the interpreter, which
        # renders it as a traceback and exits 1 — this client's published code
        # for « the control plane answered deny », for a file the invocation
        # merely NAMED and about which no question was ever put (articles 1 and
        # 2). Both sibling readers of an untrusted document already catch it.
        raise PackInvalid(
            f"{MANIFEST_FILE} does not read as a manifest: the manifest nests deeper "
            f"than this reader parses ({too_deep})"
        ) from too_deep
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as unreadable:
        raise PackInvalid(
            f"{MANIFEST_FILE} does not read as a manifest: {unreadable}"
        ) from unreadable
    if "pack" not in document or not isinstance(document["pack"], dict):
        raise PackInvalid(
            f"[pack] is missing: {MANIFEST_FILE} declares the pack itself in a [pack] "
            f"table, before any point"
        )
    header = _declared(document["pack"], PACK_MEMBERS)
    return Pack(
        name=_a_pack_name(header["name"]),
        classification=_a_classification(header["classification"]),
        classified_on=_a_date(header["classified_on"]),
        points=_the_points(document),
        directory=path,
    )


def _declared(table: dict[str, object], members: tuple[str, ...]) -> dict[str, object]:
    """The table with every expected member present, the ones it omits as `None`."""
    return {member: None for member in members} | table


def _a_pack_name(value: object) -> str:
    if not isinstance(value, str) or _PACK_NAME.fullmatch(value) is None:
        raise PackInvalid(
            f"[pack].name is {value!r}: a pack name is lower-case letters, digits and "
            f"hyphens, beginning with a letter, so that one pack has one spelling"
        )
    return value


def _a_classification(value: object) -> str:
    if value != CONVENIENCE:
        raise PackInvalid(
            f"[pack].classification is {value!r}: this format admits {CONVENIENCE!r} "
            f"alone, because article 9 puts packs for sophisticated frameworks outside "
            f"the open core"
        )
    return CONVENIENCE


def _a_date(value: object) -> date:
    """The date the classification was made, refused unless it is one.

    Article 9 wants the classification dated so that it can be re-examined, which
    a date this reader could not parse would quietly prevent.
    """
    if isinstance(value, date):
        return date(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise PackInvalid(
        f"[pack].classified_on is {value!r}: the classification carries the date it was "
        f"made, as an ISO date, so that it can be re-examined rather than assumed current"
    )


def _the_points(document: dict[str, object]) -> tuple[Point, ...]:
    value = _declared(document, ("point",))["point"]
    if not isinstance(value, list) or not value:
        raise PackInvalid(
            "[[point]] is missing: a pack that declares no interposition point installs "
            "nothing, and an engine that installed nothing must not report a pack as "
            "installed (article 2)"
        )
    return tuple(_a_point(entry, index) for index, entry in enumerate(value))


def _a_point(entry: object, index: int) -> Point:
    where = f"[[point]] {index + 1}"
    if not isinstance(entry, dict):
        raise PackInvalid(f"{where} is {entry!r}: every point is declared as a table")
    declared = _declared(entry, POINT_MEMBERS)
    module = declared["module"]
    if not isinstance(module, str) or not _is_dotted_identifier(module):
        raise PackInvalid(
            f"{where} module is {module!r}: a point names the module holding the "
            f"operation to wrap, as a dotted identifier"
        )
    attribute = declared["attribute"]
    if not isinstance(attribute, str) or not _is_identifier(attribute):
        raise PackInvalid(
            f"{where} attribute is {attribute!r}: a point names one attribute of that "
            f"module, as a single identifier"
        )
    capability = _a_capability(declared["capability"], module, attribute, where)
    digest = declared["digest"]
    if (
        not isinstance(digest, list)
        or not digest
        or not all(isinstance(member, str) and _is_identifier(member) for member in digest)
    ):
        raise PackInvalid(
            f"{where} digest is {digest!r}: a point names the call arguments that form "
            f"its digest, as a non-empty list of identifiers (article 11: what is sent "
            f"is a digest, and which arguments it covers is declared, never implicit)"
        )
    audit_event = declared["audit_event"]
    if not isinstance(audit_event, str) or not audit_event:
        raise PackInvalid(
            f"{where} audit_event is {audit_event!r}: a point names the event a verifier "
            f"watches for, as a non-empty string"
        )
    return Point(
        module=module,
        attribute=attribute,
        capability=capability,
        digest=tuple(digest),
        audit_event=audit_event,
    )


def _a_capability(value: object, module: str, attribute: str, where: str) -> str:
    """One capability against both rules, the contract's shape first.

    The contract's first because it is the one a question is validated against:
    a spelling the daemon will refuse as malformed is not worth judging for
    anything else, and a pack declaring one governed nothing while appearing to
    (article 2).
    """
    rule = capability_rule()
    if (
        not isinstance(value, str)
        or rule.shape.fullmatch(value) is None
        or len(value) < rule.shortest
        or (rule.longest and len(value) > rule.longest)
    ):
        raise PackInvalid(
            f"{where} capability is {value!r}: the control plane publishes the rule for a "
            f"capability in its {ASK_REQUEST_SCHEMA} schema, and this spelling is not one "
            f"it admits — the schema states `{rule.stated}`, of {rule.shortest} to "
            f"{rule.longest if rule.longest else 'any number of'} characters. Written out "
            f"plainly rather than escaped, so it "
            f"can be compared with the spelling above. A capability the plane refuses as "
            f"malformed is a question this pack could never ask."
        )
    borrowed = _a_borrowed_segment(value, module, attribute)
    if borrowed is not None:
        raise PackInvalid(
            f"{where} capability is {value!r}: a capability names a kind of effect, never "
            f"a library name (segment {borrowed!r} is one) — article 4"
        )
    return value


def _a_borrowed_segment(capability: str, module: str, attribute: str) -> str | None:
    """The capability's first segment that is a name from the point, or `None`.

    Compared segment by segment, against every segment of the module path and
    against the attribute, with the case folded on both sides.

    It is not the comparison that refuses an upper-case capability: the shape
    above does, everywhere in a capability, so a spelling like `parcel.Dispatch`
    cannot be declared at all. Comparing with the case kept therefore bought
    nothing and cost the rule its whole reach over a class name — the only
    spellings it could still catch were the ones already refused by the shape —
    so `parcel.dispatch` declared on a `Dispatch` is the library name wearing a
    capability's clothes that this rule exists for, and it is refused.

    The pair is invented and has to stay invented, for the reason the module
    docstring gives: the guard reads this file too.
    """
    borrowed = {segment.casefold() for segment in (*module.split("."), attribute)}
    return next(
        (segment for segment in capability.split(".") if segment.casefold() in borrowed), None
    )


def _is_identifier(text: str) -> bool:
    return text.isidentifier() and not keyword.iskeyword(text)


def _is_dotted_identifier(text: str) -> bool:
    return bool(text) and all(_is_identifier(part) for part in text.split("."))
