# SPDX-License-Identifier: Apache-2.0
"""The engine knows no library, read off the engine's own source.

    "The engine knows no library. It reads manifests and installs what they
    declare. A library name may appear in a pack; it may never appear in the
    engine — not as an identifier, not as a string, not in a docstring. This is
    article 4's vocabulary rule applied to the one component most likely to
    erode it, since an engine is exactly where a special case for a popular
    library is cheapest to add and hardest to see. The guard is written in the
    same change as the engine, and it walks the engine's source rather than
    consulting a list of forbidden names: a deny-list would need to know the
    names to forbid, and would go silent on the first one nobody thought of."
                            — the instrumentation chain architecture, 2026-09-14

So the vocabulary is read from the shipped packs rather than written here, and
the engine's source is parsed rather than grepped: a name that reaches the
engine through a docstring is as much a special case as one in an `if`.

Three clauses.

**Both halves of a pack's vocabulary are scanned for inside every string, and
both are compared to whole tokens.** A declared module is a library name —
nothing else is spelled that way — so finding one anywhere in a docstring is
finding the special case. An attribute used to be compared only to a whole
token, on the argument that a declared attribute may be an ordinary word
(`run`, `get`, `open`) and that scanning prose for those would fire on text
about nothing in particular. The first shipped pack showed what that reasoning
cost: `manifest.py` spelled the shipped pack's own declared attribute inside a
docstring, to illustrate case-sensitivity, and the whole-token rule could not
see it — so the file that states article 4's vocabulary rule was the file
breaking it, in the one place a reader would go to learn the rule. Attributes
are scanned inside strings now, and the cost is stated rather than dodged: a
pack that declares an ordinary word as its attribute will make prose carrying
that word a violation in these three files, and the answer then is to reword
the prose. An inconvenience that arrives as a red test is worth more than a
clause that cannot see the defect it was written for.

**A `bytes` literal is a string literal.** `b"…"` is read exactly like `"…"`,
by both clauses, because the rule quoted above admits no third kind of literal
and a reader of the source would not tell them apart. Found by a review that
measured three ordinary one-line spellings of the defect passing this guard in
silence, `literal()` says what it costs to decode them, and the split string
this guard openly does not chase (`"sub" + "process"`, an f-string with a hole)
is a different thing: adjacent literals are one constant at parse time and were
already caught.

**An import is an identifier too.** `tokens()` collects the names an `import`
binds — the dotted name, its first segment, and what a `from … import …` takes
— because `import <library>` is the most literal spelling of « the engine knows
a library », and an `ast.alias` is not an `ast.Name`. Found by the same review,
which put one `import` line into this file's own subject and watched the guard
say nothing.

**One exemption on the attribute clause, and it is the seam's own two names.**
Since the engine supplies the invocation's scope to the ask, the boundary's
published method name is IN `engine.py` — as this project's own API, not as a
library's — in code and in the prose that explains it. `request` and
`record_outcome` are therefore exempt from the attribute comparison, token and
string alike, and the exemption is read off `sayfirst_boundary` rather than
written down: a name is exempt only while the boundary runtime actually
publishes it on the type the seam names. A library name could only become
exempt by becoming part of this project's own boundary, which is a decision and
not a leak. Modules are NOT exempted this way, so a library literally called
`request` would still be caught.

**A whole string that is a dotted module path is refused whatever it names**,
because that is the shape of the defect the clause above cannot see: a path this
repository's own vocabulary does not cover. Two exemptions, both narrow:
anything under this project's own `sayfirst_` names, and the pack format's own
file names, which are dotted identifiers by coincidence of spelling. The second
cannot be widened — a test below holds it against the format itself.

The `subprocess` pack (article 9's first) ships now, so the first clause has a
real vocabulary to bite on — `test_the_real_shipped_pack_supplies_the_vocabulary`
holds `declared(shipped())` against it directly, rather than trusting that the
parametrized test below found something. Before it shipped, the shipped
vocabulary was empty and that clause had nothing to bite on; the mechanism was
proven on a planted pack instead, which the last two tests below still do,
because a guard that only ever saw the one real pack it ships with is not
proven against a *second* one.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Final

import pytest

from sayfirst_cli.instrument import manifest

REPOSITORY = Path(__file__).resolve().parents[1]
INSTRUMENT = REPOSITORY / "src" / "sayfirst_cli" / "instrument"
PACKS = REPOSITORY / "src" / "sayfirst_cli" / "packs"

#: The five files the rule binds: the engine, the launcher, the reader of what a
#: pack declares, the verifier's harness, and the package's own `__init__.py`.
#: Everything else in this distribution may name what it likes; these are the
#: ones a library name would give power to.
#:
#: The harness joined them with layer 3, and for the engine's own reason. Its
#: whole job is to watch for the audit events the designated manifests name, so
#: one library's event name spelled inside it would be exactly article 4's
#: special case, arriving in the one component whose value is that it is
#: impartial about what it watches. `verify.py` is deliberately NOT here: it is
#: the command layer, like `commands.py`, and starting a second interpreter is
#: the one thing it does that a library name is unavoidable for.
#:
#: `__init__.py` joined it to close a laundering route: a name re-exported from
#: `__init__.py` under a euphemism was invisible to this guard, because nothing
#: scanned the file that performed the re-export. See `own_origin_names` below
#: for the exemption that made the re-export unnecessary in the first place.
GUARDED = ("engine.py", "launch.py", "manifest.py", "harness.py", "__init__.py")

#: The four of `GUARDED` substantial enough for the size-based anti-vacuity
#: check below to mean anything. `__init__.py` is a docstring first and almost
#: nothing else by design — that is exactly the state that keeps it safe — so
#: a size threshold calibrated to the other four would flag the file for being
#: exactly what it should be. `test_the_package_init_actually_parsed_to_something_too`
#: is `__init__.py`'s own, differently calibrated, anti-vacuity check.
SUBSTANTIAL = GUARDED[:4]

#: What a dotted module path looks like, and nothing else does.
DOTTED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+")

#: This project's own names, which are not a library this engine knows.
OWN_PREFIX = "sayfirst_"

#: The suffixes the pack format's own file names carry. A name exempted below
#: must end in one of them, so the exemption cannot quietly admit a module path.
FORMAT_SUFFIXES = frozenset({"toml", "py", "md"})


def source(name: str) -> str:
    return (INSTRUMENT / name).read_text(encoding="utf-8")


def literal(node: ast.AST) -> str | None:
    """The text of a string constant — a `bytes` literal included — or `None`.

    A `bytes` literal is a string literal to every reader, and the rule quoted
    above is absolute: not as an identifier, not as a string, not in a
    docstring. Collecting only `str` left `b"…"` reaching neither `tokens()`
    nor `strings()`, which a review measured as the one evasion here that is
    neither obfuscation nor covered — not the split string this guard openly
    does not chase, but one ordinary literal, the kind an author writes without
    meaning anything by it, in the file where a special case is « cheapest to
    add and hardest to see ».

    Decoded with `errors="ignore"`, because the question is whether a library's
    name is in there and a byte that is not text cannot be part of one.
    """
    if not isinstance(node, ast.Constant):
        return None
    if isinstance(node.value, str):
        return node.value
    if isinstance(node.value, bytes):
        return node.value.decode(errors="ignore")
    return None


def tokens(text: str) -> set[str]:
    """Every name, import and string the source carries, docstrings included.

    An import contributes the dotted name, its first segment and the names it
    binds: `import a.b`, `import a.b as c` and `from a.b import c` all name
    `a.b` and `a`, and none of them is an `ast.Name`.
    """
    collected: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Name):
            collected.add(node.id)
        elif isinstance(node, ast.Attribute):
            collected.add(node.attr)
        elif isinstance(node, ast.arg):
            collected.add(node.arg)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                collected.update({alias.name, alias.name.split(".")[0]})
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                collected.update({node.module, node.module.split(".")[0]})
            collected.update(alias.name for alias in node.names)
        elif (value := literal(node)) is not None:
            collected.add(value)
    return collected


def strings(text: str) -> list[str]:
    """Every string constant, which is where a docstring lives too.

    A `bytes` literal is one of them; `literal` says why and how it is read.
    """
    found = (literal(node) for node in ast.walk(ast.parse(text)))
    return [value for value in found if value is not None]


def declared(directories: list[Path]) -> tuple[frozenset[str], frozenset[str]]:
    """The modules and attributes the shipped packs name, read from the packs.

    A module contributes its dotted name AND its top-level package, because the
    top-level package is the library name and naming it is enough to
    special-case everything under it. Deeper segments are deliberately not
    added: the second half of a dotted path is an ordinary word — `client`,
    `request`, `core` — and forbidding those would fire on prose that has
    nothing to do with any library, which is how a guard comes to be loosened
    by the person it inconveniences.
    """
    modules: set[str] = set()
    attributes: set[str] = set()
    for directory in directories:
        for point in manifest.read_pack(directory).points:
            modules.add(point.module)
            modules.add(point.module.split(".")[0])
            attributes.add(point.attribute)
    return frozenset(modules), frozenset(attributes)


def exempt() -> frozenset[str]:
    """The pack format's own file names, which are the engine's vocabulary."""
    return frozenset(manifest.REQUIRED_FILES)


def seam_names() -> frozenset[str]:
    """The two names the boundary seam publishes, read off the boundary runtime.

    The architecture's seam sentence is « the engine calls only
    `request(capability, arguments)` and the grant's `record_outcome(digest)` ».
    A name here is exempt from the ATTRIBUTE comparison only while the boundary
    runtime really publishes it as a callable on the type the seam names, so the
    exemption cannot be widened by editing this file — it would take widening
    this project's own boundary.
    """
    from sayfirst_boundary import Boundary, GrantHandle

    published = {"request": Boundary, "record_outcome": GrantHandle}
    return frozenset(
        name for name, owner in published.items() if callable(getattr(owner, name, None))
    )


def own_origin_names(text: str) -> frozenset[str]:
    """Names THIS file took from this project's own packages, and nothing else.

    This replaces a re-export that tried to solve the same problem the wrong way
    (a name moved into `instrument/__init__.py` under a euphemism, which
    laundered a real library reference past this guard one file over —
    `GUARDED` now includes `__init__.py`, which is the other half of closing
    that route).

    A `from sayfirst_… import connect` line binds `connect` — this project's
    own name, proven by the import itself rather than assumed from the
    spelling. Origin-scoped and per-file: only a `node.module` that actually
    starts with `OWN_PREFIX` exempts anything, and only in the file that
    carries that import — a bare `connect` elsewhere, imported from
    somewhere else or not imported at all, is not covered by this and is
    still caught by the token check below.

    Only the ORIGIN name is exempt — `alias.name`, the one `tokens()` collects
    for the import line itself. An alias is not: `from sayfirst_… import
    Answered as Popen` would otherwise bless a library's attribute name under
    an own-origin import, which is exactly the rename the token rule refuses.
    The exemption is a fact about the import line, not about every later
    spelling in the file: a bare `m.connect` on some other object is not
    told apart from the imported name by this check — the same cost the seam
    exemption carries — which is why the alarm below watches what the
    shipped packs declare against these names.
    """
    bound: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith(OWN_PREFIX)
        ):
            bound.update(alias.name for alias in node.names)
    return frozenset(bound)


def violations(text: str, modules: frozenset[str], attributes: frozenset[str]) -> list[str]:
    """Every way this source knows a library, said one line each."""
    found = []
    # The seam's own names are exempted from the attribute half alone: a module
    # spelled like one of them is still a library and is still caught.
    named = attributes - seam_names()
    forbidden = modules | named
    # A name THIS file bound through `from sayfirst_… import …` is this
    # project's own name, not a library's — exempted from the token check
    # alone (never from the string-prose scan below, which is not tied to any
    # specific AST binding and so cannot be vouched for the same way).
    exempted = own_origin_names(text)
    for name in sorted((tokens(text) & forbidden) - exempted):
        found.append(f"it names {name!r}")
    for value in strings(text):
        for name in sorted(modules):
            if re.search(rf"\b{re.escape(name)}\b", value):
                found.append(f"a string names the module {name!r}")
        for name in sorted(named):
            if re.search(rf"\b{re.escape(name)}\b", value):
                found.append(f"a string names the attribute {name!r}")
    for value in strings(text):
        matched = DOTTED.fullmatch(value)
        if matched is None or value.startswith(OWN_PREFIX) or value in exempt():
            continue
        found.append(f"a string is the dotted module path {value!r}")
    return found


def shipped() -> list[Path]:
    """Every pack this distribution ships, read straight off the source tree.

    A directory counts by carrying a manifest, not merely by sitting under
    `packs/`: a `__pycache__` left behind by importing something beside the
    packs (`packs/__init__.py`, loaded as an ordinary module) is a directory
    too, and reading it as a pack would break this walk on whichever day
    Python happened to cache one.
    """
    if not PACKS.is_dir():
        return []
    return sorted(
        item
        for item in PACKS.iterdir()
        if item.is_dir() and (item / manifest.MANIFEST_FILE).is_file()
    )


@pytest.mark.parametrize("name", GUARDED)
def test_no_shipped_packs_vocabulary_appears_in_the_engine(name: str) -> None:
    """The rule itself, against whatever is shipped on the day it runs."""
    modules, attributes = declared(shipped())
    assert violations(source(name), modules, attributes) == []


def test_the_real_shipped_pack_supplies_the_vocabulary() -> None:
    """Anti-vacuity for the parametrized test above: `shipped()` now finds three
    packs (article 9 names three convenience packs, and the second and third
    shipped alongside this test) and this is the vocabulary they must have
    found — proving the test above bites on something real rather than passing
    over an empty walk.

    `request` is deliberately not asserted here even though `http-client`'s
    point is on `urllib.request`: `declared()`'s own docstring says a module
    contributes its full dotted name and its top-level package alone —
    `urllib.request` and `urllib` — and deliberately not a deeper segment,
    because a deeper segment is an ordinary word. `urllib` is therefore the
    word this pack adds to the module vocabulary, not `request`.
    """
    modules, attributes = declared(shipped())
    assert "subprocess" in modules
    assert "Popen" in attributes
    assert modules >= {"urllib", "urllib.request", "sqlite3"}
    assert attributes >= {"urlopen", "connect"}
    for name in GUARDED:
        assert violations(source(name), modules, attributes) == []


@pytest.mark.parametrize(
    "mutation",
    [
        "\n\nimport subprocess\n",
        "\n\nimport subprocess as _module\n",
        "\n\nfrom subprocess import Popen\n",
        '\n\n_NOTE = """spelled `process.popen` versus `process.Popen`."""\n',
        '\n\n_NOTE = """This one special-cases Popen, which it must not."""\n',
        '\n\n_SPECIAL = b"subprocess"\n',
        '\n\n_SPECIAL = b"Popen"\n',
        '\n\n_SPECIAL = b"urllib.request"\n',
        '\n\n_SPECIAL = "sub" "process"\n',
    ],
)
def test_the_shapes_the_guard_used_to_miss_are_caught_on_the_real_vocabulary(
    mutation: str,
) -> None:
    """The three holes a review found, held against the packs that actually ship.

    An `import` naming the module, in each of its three spellings — an
    `ast.alias` is not an `ast.Name`, and this is the most literal way to write
    « the engine knows a library ». The declared attribute inside a docstring:
    the fourth mutation is the sentence `manifest.py` really carried, which
    passed this guard while the rule it illustrates was being broken by the
    illustration. And the `bytes` literal, in each half of the vocabulary and
    as a dotted path: three ordinary lines that reached neither clause while
    only `str` constants were collected.

    The last mutation is the adjacent-literal pair, which was already caught —
    kept beside the three above because it is what tells « a literal this guard
    reads » from « the split string it openly does not chase »: a reader who
    finds the bytes rows here should be able to see which neighbouring shape is
    covered for a different reason.
    """
    modules, attributes = declared(shipped())
    clean = source("engine.py")
    assert violations(clean, modules, attributes) == []
    assert violations(clean + mutation, modules, attributes) != []


@pytest.mark.parametrize("name", SUBSTANTIAL)
def test_the_source_actually_parsed_to_something(name: str) -> None:
    """Anti-vacuity: a check over an empty token set passes without looking."""
    collected = tokens(source(name))
    assert len(collected) > 20, sorted(collected)


def test_the_package_init_actually_parsed_to_something_too() -> None:
    """The same anti-vacuity as above, calibrated to a file that stays this
    thin on purpose. `__init__.py` is a module docstring and nothing else at
    HEAD — `tokens()` finds exactly one entry, the docstring itself — so the
    bar here is only that parsing found it at all, not that there is 20 of
    anything: a `> 20` bar on a file this size would flag the file for being
    exactly the shape article 4 wants it to stay."""
    collected = tokens(source("__init__.py"))
    assert len(collected) >= 1, sorted(collected)


def test_the_format_file_exemption_cannot_be_widened() -> None:
    """The three exempted names are file names, and none of them names a module.

    Without this, the exemption is a hole the width of whatever somebody adds to
    the pack format's file list — a library path put there would pass the dotted
    clause everywhere in the engine.
    """
    modules, attributes = declared(shipped())
    for name in exempt():
        stem, _, suffix = name.rpartition(".")
        assert suffix in FORMAT_SUFFIXES, name
        assert stem not in modules | attributes, name
        assert DOTTED.fullmatch(name) is not None, name


def plant(root: Path, *, module: str, attribute: str) -> Path:
    """A pack that declares a library this engine must not know."""
    directory = root / "planted"
    directory.mkdir()
    (directory / manifest.MANIFEST_FILE).write_text(
        '[pack]\nname = "planted"\nclassification = "convenience"\n'
        "classified_on = 2026-09-14\n\n[[point]]\n"
        f'module = "{module}"\nattribute = "{attribute}"\n'
        'capability = "example.effect"\ndigest = ["first"]\n'
        f'audit_event = "{module}.{attribute}"\n',
        encoding="utf-8",
    )
    (directory / manifest.EXECUTION_MODULE).write_text("def wrap(a, b, c):\n    return a\n")
    (directory / manifest.CLASSIFICATION_NOTE).write_text("planted\n")
    return directory


@pytest.mark.parametrize(
    "mutation",
    [
        "\n\nplantedlib = None\n",
        '\n\n_SPECIAL = "plantedlib.core"\n',
        "\n\n\ndef _special(thing):\n    return thing.PlantedThing\n",
        '\n\n_NOTE = """This one special-cases plantedlib, which it must not."""\n',
        '\n\n_NOTE = """It mentions PlantedThing in prose, which it must not."""\n',
        "\n\nimport plantedlib.core\n",
        "\n\nfrom plantedlib import core\n",
        '\n\n_SPECIAL = b"plantedlib.core"\n',
        '\n\n_SPECIAL = b"PlantedThing"\n',
    ],
)
def test_the_check_would_have_failed_on_a_planted_library(tmp_path: Path, mutation: str) -> None:
    """The guard watched firing, on the engine's real source plus one line.

    Each mutation is a form the defect actually takes: an identifier, a string,
    an attribute read, a docstring that admits to the special case, a docstring
    that merely spells the attribute, and the two import spellings.
    """
    directory = plant(tmp_path, module="plantedlib.core", attribute="PlantedThing")
    modules, attributes = declared([directory])
    clean = source("engine.py")
    assert violations(clean, modules, attributes) == []
    assert violations(clean + mutation, modules, attributes) != []


def test_a_dotted_path_no_pack_declared_is_caught_too(tmp_path: Path) -> None:
    """The clause that does not need a vocabulary, which is why it exists."""
    clean = source("engine.py")
    assert violations(clean, frozenset(), frozenset()) == []
    assert violations(clean + '\n\n_LOADED = "someother.module"\n', frozenset(), frozenset())


def test_the_two_exemptions_are_the_only_ones(tmp_path: Path) -> None:
    """Named so that widening them is a diff rather than a discovery."""
    clean = source("engine.py")
    permitted = f'\n\n_OURS = "{manifest.MANIFEST_FILE}"\n_MINE = "sayfirst_contract.client"\n'
    assert violations(clean + permitted, frozenset(), frozenset()) == []
    assert violations(clean + '\n\n_OTHER = "other_project.client"\n', frozenset(), frozenset())


def test_the_seam_exemption_is_the_boundarys_own_two_names() -> None:
    """Read off the boundary runtime, so this file cannot widen it on its own."""
    assert seam_names() == frozenset({"request", "record_outcome"})


def test_the_seam_exemption_does_not_exempt_a_module_of_the_same_name() -> None:
    """A library called `request` is still a library, and is still caught."""
    clean = source("engine.py")
    assert violations(clean, frozenset({"request"}), frozenset()) != []
    assert violations(clean, frozenset(), frozenset({"request"})) == []


def test_the_seam_exemption_exempts_nothing_else(tmp_path: Path) -> None:
    """Every other attribute a pack declares is compared as before."""
    directory = plant(tmp_path, module="plantedlib.core", attribute="PlantedThing")
    modules, attributes = declared([directory])
    assert "PlantedThing" not in seam_names()
    assert (
        violations(source("engine.py") + "\n\nx = 1  # PlantedThing\n", modules, attributes) == []
    )
    assert (
        violations(
            source("engine.py") + "\n\n\ndef _s(thing):\n    return thing.PlantedThing\n",
            modules,
            attributes,
        )
        != []
    )


def no_seam_name_is_interposed(directories: list[Path]) -> None:
    """The alarm itself, so that the test below can watch it fire.

    A companion that re-derived this expression would prove the expression
    works and nothing about the rule the gate runs; this is the rule.
    """
    _, attributes = declared(directories)
    collided = sorted(attributes & seam_names())
    assert collided == [], (
        f"a pack declares {collided} as an attribute it interposes, and those names are "
        f"exempt from the attribute clause of this guard: either the pack renames its "
        f"point or the exemption stops being safe"
    )


def test_no_shipped_pack_declares_a_point_on_a_seam_name() -> None:
    """The alarm on the exemption above, and the reason the exemption needs one.

    `request` and `record_outcome` are exempt from the attribute comparison
    because they are this project's own boundary seam, and the engine has to
    name `request` in order to supply the invocation's scope to an ask. That
    exemption is sound only while no pack interposes an attribute of one of
    those names: a pack that declared `request` as the attribute it wraps would
    put a real interposed name into the exempt set, and the guard would go
    quiet about exactly the special case it exists to catch.

    So the exemption is watched rather than trusted. This fires on the packs
    that SHIP, which is where the collision would have to happen to matter —
    a pack a person wrote and named on their own command line is their code,
    and this repository's guard is about what this repository publishes.
    """
    no_seam_name_is_interposed(shipped())


@pytest.mark.parametrize("seam", sorted(seam_names()))
def test_the_alarm_fires_on_a_pack_that_declares_a_seam_name(tmp_path: Path, seam: str) -> None:
    """The alarm watched firing, once per exempted name, on a planted pack.

    Anti-vacuity for the test above, which passes today by there being nothing
    to find: without this, « the intersection is empty » would read the same
    whether the rule worked or the sets never met.
    """
    directory = plant(tmp_path, module="plantedlib.core", attribute=seam)
    with pytest.raises(AssertionError, match=seam):
        no_seam_name_is_interposed([directory])
    # And it stays quiet on a pack that interposes something else, so the alarm
    # is the seam names and not « any planted pack at all ».
    other = tmp_path / "other"
    other.mkdir()
    no_seam_name_is_interposed([plant(other, module="plantedlib.core", attribute="PlantedThing")])


# --- the origin exemption ---------------------------------------------------
#
# `own_origin_names` replaces a re-export that tried to solve the same problem
# (`harness.py` legitimately importing `connect` from `sayfirst_contract`,
# which collides with the `database` pack's own declared attribute) the wrong
# way: moving the name into `instrument/__init__.py` under a euphemism, which
# laundered the real spelling past this guard one file over. The tests below
# hold the three properties a review asked this exemption to have, that the
# re-export did not: narrow by origin, narrow by provenance, and closed
# against the laundering route it replaced.


def test_harness_keeps_its_own_connect_import_and_the_guard_stays_quiet() -> None:
    """The measured claim the fix is built on: `harness.py`'s real, unrenamed
    `connect` import (from `sayfirst_contract.transport.socket_client`) is
    clean against the real shipped vocabulary, `database`'s `connect`
    attribute included — with no rename anywhere."""
    modules, attributes = declared(shipped())
    assert "connect" in attributes
    assert violations(source("harness.py"), modules, attributes) == []


def test_the_origin_exemption_is_scoped_to_a_sayfirst_prefixed_module(tmp_path: Path) -> None:
    """Narrowness probe 1 (the reviewer's): only a `node.module` that actually
    starts with `sayfirst_` exempts anything. A `from someotherlib import
    connect` in a guarded file is not this project's own name and still
    fires, even though the local name is spelled identically."""
    modules, attributes = declared(shipped())
    clean = source("engine.py")
    mutation = "\n\nfrom someotherlib import connect\n"
    assert violations(clean, modules, attributes) == []
    assert violations(clean + mutation, modules, attributes) != []


def test_the_origin_exemption_does_not_cover_a_name_not_imported_from_sayfirst(
    tmp_path: Path,
) -> None:
    """Narrowness probe 2 (the reviewer's): a bare `connect` identifier that
    did NOT arrive through a `from sayfirst_… import …` line in THIS file is
    not covered, even though `connect` is exempt in `harness.py` — the
    exemption is a fact about the import line the guard read in a given file,
    never a blanket amnesty for the spelling everywhere."""
    modules, attributes = declared(shipped())
    clean = source("engine.py")
    assert "connect" not in own_origin_names(clean)
    mutation = "\n\n\ndef _f(connect):\n    return connect\n"
    assert violations(clean, modules, attributes) == []
    assert violations(clean + mutation, modules, attributes) != []


def test_the_laundering_route_through_init_is_closed() -> None:
    """Narrowness probe 3 (the reviewer's): `__init__.py` is itself guarded
    now, so the exact two-step the review measured — a re-export placed in
    `__init__.py` under a euphemism, then imported by name into `harness.py`
    — is caught at the re-export's own site, before a second file could ever
    hide it. `harness.py`'s own text is irrelevant to this probe: the point is
    that `__init__.py` no longer passes with a library import sitting in it."""
    modules, attributes = declared(shipped())
    clean = source("__init__.py")
    mutation = "\n\nfrom sqlite3 import connect as _open_it\n"
    assert violations(clean, modules, attributes) == []
    assert violations(clean + mutation, modules, attributes) != []


def guarded_origin_names() -> frozenset[str]:
    """Every name any `GUARDED` file has legitimately bound from this
    project's own `sayfirst_…` packages — the exemption's real width, read off
    the files it protects rather than a hardcoded list, the same way
    `declared()` reads the forbidden vocabulary off the packs rather than off
    a list someone maintains by hand."""
    collected: set[str] = set()
    for name in GUARDED:
        collected |= own_origin_names(source(name))
    return frozenset(collected)


#: The one collision this exemption exists for, reviewed and accepted:
#: `database`'s own declared attribute is `connect`, and `harness.py`
#: legitimately imports `connect` from
#: `sayfirst_contract.transport.socket_client` — the transport's own opening
#: call, unrelated to any pack. Unlike the seam names, this is not a
#: hardcoded exemption —
#: it is a *consequence*, derived from what `harness.py` actually imports —
#: so this constant is not itself the exemption; it is the alarm's baseline,
#: naming what is already known so the alarm below can say what is NEW.
KNOWN_ORIGIN_COLLISIONS: Final[frozenset[str]] = frozenset({"connect"})


def no_pack_collides_with_a_sayfirst_origin_name(
    directories: list[Path], exempted: frozenset[str], *, known: frozenset[str] = frozenset()
) -> None:
    """The alarm on the origin exemption, so it is watched rather than
    trusted — the same shape as `no_seam_name_is_interposed` above, for the
    same reason: a pack whose declared vocabulary collides with a name some
    guarded file legitimately imports from `sayfirst_…` would put a real
    interposed name into the exempt set, and the guard would go quiet about
    exactly the case it exists to catch. `known` exists because — unlike the
    seam names, which no shipped pack has ever collided with — this
    exemption's whole reason for existing is a collision that is already
    real and already reviewed (`database`'s `connect`); asserting the
    intersection is empty would make the alarm permanently red for a state
    this fix round deliberately produces. Anything BEYOND `known` is new and
    unreviewed, and that is what fails.
    """
    modules, attributes = declared(directories)
    # `known` excuses an attribute name only: a pack declaring a MODULE whose
    # name is an own-origin import would be a different collision entirely.
    collided = sorted((modules & exempted) | ((attributes & exempted) - known))
    assert collided == [], (
        f"a pack declares {collided} as a module or attribute it interposes, and some "
        f"guarded file imports that same name from this project's own `sayfirst_…` "
        f"packages: either the pack renames its point, or this collision is reviewed and "
        f"added to `KNOWN_ORIGIN_COLLISIONS`"
    )


def test_no_shipped_pack_collides_with_a_guarded_sayfirst_import_beyond_the_known_one() -> None:
    """The regression guard: today's real collision is exactly the reviewed
    one (`database`'s `connect`) and nothing else. A second, unreviewed
    collision — a future pack choosing an attribute that also happens to be
    a name some guarded file imports from `sayfirst_…` — fails here rather
    than silently riding through on the existing exemption."""
    no_pack_collides_with_a_sayfirst_origin_name(
        shipped(), guarded_origin_names(), known=KNOWN_ORIGIN_COLLISIONS
    )


def test_the_origin_alarm_fires_on_an_unreviewed_collision(tmp_path: Path) -> None:
    """Anti-vacuity for the test above: a pack declaring a point on some name
    a guarded file legitimately imports, OTHER than the one reviewed
    collision, must still be caught — `known` narrows the alarm to what has
    been reviewed, not to nothing.
    """
    # The REAL exempt set, and a real member of it that no reviewed collision
    # covers, so an empty set could never make this probe pass.
    exempted = guarded_origin_names()
    unreviewed = sorted(exempted - KNOWN_ORIGIN_COLLISIONS)
    assert unreviewed, "the guarded files import nothing own-origin but the reviewed name"
    directory = plant(tmp_path, module="plantedlib.core", attribute=unreviewed[0])
    with pytest.raises(AssertionError, match=unreviewed[0]):
        no_pack_collides_with_a_sayfirst_origin_name(
            [directory], exempted, known=KNOWN_ORIGIN_COLLISIONS
        )
    # And it stays quiet on the one collision that IS reviewed.
    other = tmp_path / "other"
    other.mkdir()
    no_pack_collides_with_a_sayfirst_origin_name(
        [plant(other, module="plantedlib.core", attribute="connect")],
        exempted,
        known=KNOWN_ORIGIN_COLLISIONS,
    )


def test_the_reviewed_collision_baseline_is_exactly_what_was_reviewed() -> None:
    """`KNOWN_ORIGIN_COLLISIONS` is the one exemption a later edit could widen
    silently; it is held to the single reviewed name, and to a name some
    guarded file really does import from this project's own packages."""
    assert frozenset({"connect"}) == KNOWN_ORIGIN_COLLISIONS
    assert guarded_origin_names() >= KNOWN_ORIGIN_COLLISIONS
