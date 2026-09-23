# SPDX-License-Identifier: Apache-2.0
"""How `--pack` is read: a path is a directory, and a bare word is a shipped pack's name.

Article 9 asks for a pack to be « explicitly designated by the user » and
forbids a registry. A person who types `--pack` and the name of a pack this
distribution ships has designated it, explicitly; what would be a registry is
anything that made the answer depend on something other than what they typed
and what this distribution carries — a search path, a directory consulted on
the way, a name somebody else can publish under. So the rule is about the
SPELLING and nothing else:

* a designation with a path separator in it (or `.`, or `..`) is a directory,
  read exactly as it always was;
* anything else is the name of a pack inside this installed distribution, and a
  name it does not ship is refused — the working directory is never consulted
  for it, so a directory somebody left there cannot become the code that runs.

The cases below hold both halves, and the two ways they could leak into each
other.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from governed_programs import SPAWNING_APP, instrument, plant_spawn_pack
from sayfirst_contract_stub.stub import Stub
from sayfirst_contract_stub.stub_http import serve

from sayfirst_cli import exit_codes, packs_cmd
from sayfirst_cli.instrument import designation, manifest

SHIPPED = {path.name: path for path in packs_cmd.shipped_packs()}


def test_this_distribution_ships_the_three_packs_these_cases_name() -> None:
    assert set(SHIPPED) == {"database", "http-client", "subprocess"}


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_a_shipped_pack_is_designated_by_its_name(name: str) -> None:
    resolved = designation.directory_of(name)
    assert resolved == SHIPPED[name]
    # The name a person types is the name the pack gives itself, so that one
    # pack has one spelling: a directory name that drifted from its manifest
    # would make `packs list` print one word and `--pack` take another.
    assert manifest.read_pack(resolved).name == name


def test_a_designation_with_a_separator_is_that_directory_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    own = plant_spawn_pack(tmp_path, name="subprocess")
    monkeypatch.chdir(tmp_path)
    assert designation.directory_of("./subprocess") == Path("./subprocess")
    assert designation.directory_of(str(own)) == own
    assert manifest.read_pack(designation.directory_of("./subprocess")).name == "process-effects"


def test_a_bare_name_never_reads_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory of the same name beside the program is not the pack that runs."""
    plant_spawn_pack(tmp_path, name="subprocess")
    monkeypatch.chdir(tmp_path)
    assert designation.directory_of("subprocess") == SHIPPED["subprocess"]


def test_a_bare_word_that_names_no_shipped_pack_is_refused_with_the_way_to_say_a_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plant_spawn_pack(tmp_path, name="mine")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(manifest.PackInvalid) as refusal:
        designation.directory_of("mine")
    said = str(refusal.value)
    assert "database, http-client, subprocess" in said
    assert "./mine" in said


@pytest.mark.parametrize("spelling", [".", "..", "../packs/own", "/srv/packs/own", "own/"])
def test_these_spellings_are_paths(spelling: str) -> None:
    assert designation.directory_of(spelling) == Path(spelling)


@pytest.mark.parametrize(
    "spelling", ["", "Subprocess", "sub process", "~subprocess", "sub_process"]
)
def test_a_bare_word_that_could_not_be_a_pack_name_is_refused(spelling: str) -> None:
    with pytest.raises(manifest.PackInvalid):
        designation.directory_of(spelling)


def test_a_governed_run_takes_a_shipped_pack_by_name(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run", "--pack", "subprocess", "--socket", str(socket_path), "--scope", "local",
            "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert stub.decision_count == 1


def test_a_governed_run_still_takes_a_directory_of_ones_own(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    plant_spawn_pack(tree, name="own-pack")
    stub = Stub("allow")
    with serve(stub, tmp_path / "d.sock") as socket_path:
        finished = instrument(
            "run", "--pack", "./own-pack", "--socket", str(socket_path), "--scope", "local",
            "--", "app.py", cwd=tree,
        )  # fmt: skip
    assert finished.returncode == 0, finished.stderr
    assert stub.decision_count == 1


def test_a_name_nothing_ships_is_a_misuse_before_anything_runs(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text('print("ran")\n', encoding="utf-8")
    for verb in ("run", "verify"):
        finished = instrument(
            verb, "--pack", "no-such-pack", "--socket", str(tmp_path / "absent.sock"),
            "--scope", "local", "--", "app.py", cwd=tree,
        )  # fmt: skip
        assert finished.returncode == exit_codes.EXIT_MISUSE, (verb, finished.stderr)
        assert finished.stderr.startswith("no-such-pack: "), finished.stderr
        assert "ran" not in finished.stdout


def test_packs_check_reads_a_designation_the_way_the_engine_will() -> None:
    out, err = io.StringIO(), io.StringIO()
    assert packs_cmd.main(["check", "subprocess"], out=out, err=err) == 0, err.getvalue()
    assert out.getvalue() == "ok subprocess\n"
    out, err = io.StringIO(), io.StringIO()
    assert packs_cmd.main(["check", "no-such-pack"], out=out, err=err) == exit_codes.EXIT_MISUSE
