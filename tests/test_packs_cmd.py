# SPDX-License-Identifier: Apache-2.0
"""`sayfirst packs list` and `sayfirst packs check`, read straight off `main`.

Neither verb touches a daemon or a program: `list` reads what the installed
package carries, and `check` reads one manifest the way the engine will,
before anything is ever run with it.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest

from sayfirst_cli import exit_codes, main, packs_cmd
from sayfirst_cli.instrument import manifest

REPOSITORY = Path(__file__).resolve().parents[1]
SUBPROCESS_PACK = REPOSITORY / "src" / "sayfirst_cli" / "packs" / "subprocess"

#: A pack that reads, and one whose manifest does not. The second exists
#: because `shipped_packs()` admits a directory on the strength of a `pack.toml`
#: being there, so a manifest that is present and wrong reaches both verbs.
GOOD_MANIFEST = """\
[pack]
name = "good"
classification = "convenience"
classified_on = 2026-09-15

[[point]]
module = "example_module"
attribute = "effect"
capability = "example.action"
digest = ["first"]
audit_event = "example_module.effect"
"""
BROKEN_MANIFEST = GOOD_MANIFEST.replace('name = "good"', 'name = "Not A Pack Name"')


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main.main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def plant(root: Path, directory_name: str, manifest_text: str) -> Path:
    """A pack directory of this test's own, complete but not necessarily valid."""
    directory = root / directory_name
    directory.mkdir()
    (directory / manifest.MANIFEST_FILE).write_text(manifest_text, encoding="utf-8")
    (directory / manifest.EXECUTION_MODULE).write_text(
        "def wrap(original, capability, boundary):\n    return original\n", encoding="utf-8"
    )
    (directory / manifest.CLASSIFICATION_NOTE).write_text(
        "A convenience pack written for one test.\n", encoding="utf-8"
    )
    return directory


def packs_root(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Make `shipped_packs()` walk a temporary directory instead of the installed one.

    The root is the one thing a test has to replace to plant a broken pack:
    planting one under `src/sayfirst_cli/packs` would be writing a defect into
    the distribution itself, and every guard that walks the shipped packs would
    then read it as shipped.
    """
    monkeypatch.setattr(packs_cmd.importlib.resources, "files", lambda package: root)


def test_main_dispatches_packs_to_the_packs_command() -> None:
    """The dispatch names the module and imports it when the verb is about to run.

    `main.COMMANDS` holds module names rather than functions, so that `--help`
    needs none of them; what this asserts is that the name resolves to exactly
    this command's entry point.
    """
    assert main.COMMANDS["packs"] == packs_cmd.__name__
    assert main.entry_point("packs") is packs_cmd.main


def test_list_prints_one_line_per_shipped_pack_naming_and_capability_and_path() -> None:
    code, out, err = run("packs", "list")
    assert code == 0, err
    lines = out.splitlines()
    assert lines, "no pack listed"
    assert f"subprocess process.spawn {SUBPROCESS_PACK}" in lines


def test_list_names_a_path_that_check_accepts() -> None:
    """What this runs, and no more than that.

    It was named for `instrument run` too and never invoked it; `instrument
    run` against the shipped pack is proven where a daemon can be stood up
    (`tests/test_subprocess_pack.py`), and a name here that claimed it was a
    claim this file's assertions did not support.
    """
    _, out, _ = run("packs", "list")
    path = out.splitlines()[0].split(" ")[-1]
    code, checked_out, err = run("packs", "check", path)
    assert code == 0, err
    assert checked_out.startswith("ok ")


def test_list_names_a_pack_it_could_not_read_and_prints_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken pack is what `list` has to survive.

    Sorted first on purpose: the defect this replaces printed the packs before
    it, then ended in a `PackInvalid` traceback, so the good pack after it was
    never listed at all and the exit code said nothing.
    """
    broken = plant(tmp_path, "aaa-broken", BROKEN_MANIFEST)
    good = plant(tmp_path, "zzz-good", GOOD_MANIFEST)
    packs_root(monkeypatch, tmp_path)
    code, out, err = run("packs", "list")
    assert code == exit_codes.EXIT_MISUSE
    assert out.splitlines() == [f"good example.action {good}"]
    assert str(broken) in err
    assert "[pack].name" in err


def test_list_of_packs_that_all_read_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anti-vacuity for the test above: the misuse is the broken pack's doing,
    not something this planted root does on its own."""
    plant(tmp_path, "zzz-good", GOOD_MANIFEST)
    packs_root(monkeypatch, tmp_path)
    code, out, err = run("packs", "list")
    assert (code, err) == (0, "")
    assert len(out.splitlines()) == 1


def test_check_reads_a_valid_pack_and_says_ok_with_its_name() -> None:
    code, out, err = run("packs", "check", str(SUBPROCESS_PACK))
    assert code == 0, err
    assert out == "ok subprocess\n"
    assert err == ""


def test_check_names_the_member_and_the_rule_for_an_invalid_pack(tmp_path: Path) -> None:
    empty = tmp_path / "not-a-pack"
    empty.mkdir()
    code, out, err = run("packs", "check", str(empty))
    assert code == exit_codes.EXIT_MISUSE
    assert out == ""
    assert "pack.toml" in err
    assert str(empty) in err


def test_check_of_a_directory_that_does_not_exist_is_the_same_misuse(tmp_path: Path) -> None:
    absent = tmp_path / "nowhere"
    code, out, err = run("packs", "check", str(absent))
    assert code == exit_codes.EXIT_MISUSE
    assert out == ""
    assert str(absent) in err


def test_check_of_a_manifest_nested_deeper_than_the_reader_parses_is_the_same_misuse(
    tmp_path: Path,
) -> None:
    """Exit 64 and the rule, where the reader used to let a `RecursionError` out.

    `check`'s whole promise is the one in `packs_cmd.py`'s own words — « Neither
    verb ends in a traceback » — and a traceback out of this client exits 1,
    which `exit_codes.py` publishes as « the control plane answered deny ».
    """
    deep = plant(tmp_path, "deep", "x = " + "[" * 3000 + "]" * 3000 + "\n")
    code, out, err = run("packs", "check", str(deep))
    assert code == exit_codes.EXIT_MISUSE
    assert out == ""
    assert "nests deeper than this reader parses" in err


def _a_shipped_pack_copy(root: Path, name: str) -> Path:
    """A copy of a pack this distribution really ships, outside the distribution.

    A copy rather than the path itself, so the listing under test is made of
    directories this test planted — and so nothing here can be mistaken for a
    test that writes into `src/sayfirst_cli/packs`.
    """
    source = next(
        directory
        for directory in packs_cmd.shipped_packs()
        if manifest.read_pack(directory).name == name
    )
    destination = root / f"zzz-{name}"
    shutil.copytree(source, destination)
    return destination


def test_a_broken_shipped_pack_names_it_exits_64_and_still_prints_the_others(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A manifest that does not parse at all, beside a pack that really ships.

    « The invocation was wrong » is a stretch for a pack the *distribution*
    ships, and it is the honest half of the answer: the caller typed nothing
    wrong and something the command named cannot be read. A code of its own
    would cost a number in a table three commands share, and `exit_codes.py`
    already says why its numbers are not this repository's alone to choose — so
    64's wording carries this case rather than a new number being minted for it.

    Unparseable TOML rather than a manifest that parses and breaks a rule, which
    is the test above: a reader that let the parse error out would end this
    command in a traceback and exit 1, the published code for « deny ».
    """
    broken = plant(tmp_path, "aaa-broken", "this is not toml = = =\n")
    good = _a_shipped_pack_copy(tmp_path, "subprocess")
    monkeypatch.setattr(packs_cmd, "shipped_packs", lambda: [broken, good])

    code, out, err = run("packs", "list")

    assert code == exit_codes.EXIT_MISUSE
    assert str(broken) in err
    assert f"subprocess process.spawn {good}" in out, "a broken pack silenced the readable ones"
    assert "Traceback" not in err


def _respelled(pack: Path, capability: str) -> Path:
    """The same pack with its point's capability respelled, and nothing else changed."""
    manifest_file = pack / manifest.MANIFEST_FILE
    original = manifest.read_pack(pack).points[0].capability
    manifest_file.write_text(
        manifest_file.read_text(encoding="utf-8").replace(
            f'capability = "{original}"', f'capability = "{capability}"'
        ),
        encoding="utf-8",
    )
    return pack


def test_a_capability_the_ask_schema_refuses_is_named_with_the_schemas_own_rule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The defect this rule closes, driven through the command a person types.

    An underscore is the exact spelling the client's own copy of the rule
    admitted and the control plane's schema refuses, and the cost was silent:
    the pack read, the engine installed it, and the ask was rejected as
    malformed inside somebody's program — while a policy naming the capability
    stopped the daemon starting. It is refused here instead, before anything
    runs, with the schema's own pattern in the sentence so the author can
    compare their spelling against the same text the daemon will.

    A copy of a pack this distribution really ships, respelled: the shape under
    test is a real pack's, not a fixture's.
    """
    broken = _respelled(_a_shipped_pack_copy(tmp_path, "http-client"), "net_egress")
    good = _a_shipped_pack_copy(tmp_path / "good", "subprocess")
    monkeypatch.setattr(packs_cmd, "shipped_packs", lambda: [broken, good])

    code, out, err = run("packs", "list")

    assert code == exit_codes.EXIT_MISUSE
    assert str(broken) in err
    assert manifest.ASK_REQUEST_SCHEMA in err
    assert manifest.capability_rule().stated in err
    assert f"subprocess process.spawn {good}" in out, "a broken pack silenced the readable ones"
    assert "Traceback" not in err


def test_the_same_pack_with_a_spelling_the_schema_admits_lists_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Anti-vacuity for the test above: the underscore is what the refusal is about.

    The identical copy, respelled to something the schema admits, lists and
    exits 0 — so the refusal above is the capability's spelling and not the copy,
    the temporary directory or the planted listing.
    """
    admitted = _respelled(_a_shipped_pack_copy(tmp_path, "http-client"), "net.egress")
    monkeypatch.setattr(packs_cmd, "shipped_packs", lambda: [admitted])

    code, out, err = run("packs", "list")

    assert (code, err) == (0, "")
    assert out == f"http-client net.egress {admitted}\n"
