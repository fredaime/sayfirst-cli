# SPDX-License-Identifier: Apache-2.0
"""Articles 13 and 14, as rules, with the defect planted against each of them.

`scripts/check_dependency_closure.py` measures the rule on a real install; this
file proves the rule itself catches what it exists to catch, without installing
anything. Both read the same functions, so there is no second copy to drift.
"""

from __future__ import annotations

import check_dependency_closure as guard

CLEAN = ["sayfirst-cli", "sayfirst-contract"]


def test_the_permitted_closure_is_the_client_the_contract_and_the_boundary() -> None:
    """Article 13 and article 10: the client depends on the contract and on the
    boundary runtime a governed program holds a grant in, and never on the
    server."""
    assert set(guard.PERMITTED_CLOSURE) == {
        "sayfirst-cli",
        "sayfirst-contract",
        "sayfirst-boundary",
    }
    assert "sayfirst-control-plane" not in guard.PERMITTED_CLOSURE
    assert guard.failures(CLEAN) == []


def test_a_planted_web_framework_fails_the_rule() -> None:
    """Article 14, in its own words: installing the client installs no web framework."""
    reported = guard.failures([*CLEAN, "starlette"])
    assert reported
    assert any("a web framework" in line for line in reported)


def test_a_planted_database_layer_fails_the_rule() -> None:
    """Article 14, in its own words: nor a database layer."""
    reported = guard.failures([*CLEAN, "SQLAlchemy"])
    assert reported
    assert any("a database layer" in line for line in reported)


def test_a_planted_server_distribution_fails_the_rule() -> None:
    """Article 14: the server distribution is not a dependency of the client.

    It is on neither category list, and it fails anyway: the rule is the positive
    allowlist, and the two categories only give a failure the article's words.
    """
    reported = guard.failures([*CLEAN, "sayfirst-control-plane"])
    assert reported
    assert any("does not permit" in line for line in reported)
    assert not guard.forbidden_by_category([*CLEAN, "sayfirst-control-plane"])


def test_a_name_spelled_another_way_is_the_same_name() -> None:
    """A closure is compared the way an index compares names (PEP 503)."""
    assert guard.failures(["SayFirst_CLI", "sayfirst.contract"]) == []
    assert guard.forbidden_by_category(["Psycopg2_Binary"]) == {
        "a database layer": ["psycopg2-binary"]
    }


def test_an_empty_closure_is_a_failure_and_never_a_pass() -> None:
    """An install that did not happen is not a clean closure (article 2)."""
    reported = guard.failures([])
    assert reported
    assert any("nothing was installed" in line for line in reported)


#: What `read_packs` brings back from an install that is correct: the reader
#: admits one pack, and that pack is missing none of its three files.
COMPLETE: dict[str, object] = {
    "root": "/somewhere/sayfirst_cli/packs",
    "entries": ["__init__.py", "subprocess"],
    "read": ["subprocess"],
    "packs": {"subprocess": []},
}


def test_an_install_carrying_every_pack_the_repository_ships_passes() -> None:
    """Article 9: the client ships its packs, and a pack is all three files.

    Held against what the repository ships rather than against a floor of one,
    which is the rule this used to pin: `expected` is the one pack this
    install claims to carry, so the comparison is « all of them » on a
    one-pack repository and the assertion is about the rule and not the count.
    """
    assert guard.pack_failures(COMPLETE, expected=["subprocess"]) == []
    assert guard.carried_packs(COMPLETE) == ["subprocess"]


def test_an_install_carrying_one_pack_of_three_fails_naming_the_missing() -> None:
    """The defect a floor of one passed: a wheel that shipped the first pack.

    Measured on the real step before this rule: `PASS the wheel carries 1
    pack(s): ['subprocess']`, with nothing else in the gate able to see it —
    every other reader of the packs resolves to the source tree under the
    editable install.
    """
    reported = guard.pack_failures(COMPLETE, expected=["subprocess", "http-client", "database"])
    assert reported
    assert any("not ['database', 'http-client']" in line for line in reported)
    assert any("article 9" in line for line in reported)


def test_the_rule_compares_against_the_packs_this_repository_actually_ships() -> None:
    """Anti-vacuity for the default: the right-hand side is read, not assumed.

    Without this, an `expected` that quietly came back empty would make the
    comparison above pass over any wheel at all — and the failure would be
    invisible, because every assertion in this file passes `expected` itself.
    """
    assert guard.shipped_pack_names() == ["database", "http-client", "subprocess"]
    assert guard.pack_failures(COMPLETE)  # one pack of the three this repository ships


def test_a_rule_with_nothing_to_look_for_is_a_failure_and_never_a_pass() -> None:
    """An empty right-hand side is not a clean wheel (article 2), it is no rule."""
    reported = guard.pack_failures(COMPLETE, expected=[])
    assert reported
    assert any("no pack for the step to look for" in line for line in reported)


def test_an_install_that_carries_no_pack_at_all_fails() -> None:
    """The defect the step exists for: a wheel of `.py` files and nothing else."""
    reported = guard.pack_failures(
        {**COMPLETE, "entries": ["__init__.py"], "read": [], "packs": {}}
    )
    assert reported
    assert any("no complete pack arrived" in line for line in reported)


def test_a_pack_missing_a_file_is_named_with_what_it_is_missing() -> None:
    """An exclude pattern that drops the non-Python half of a pack.

    The reader cannot see such a directory at all once its manifest is gone —
    a pack is what carries one — so the step looks at the directories under
    `packs/` as well, and says which file is not there.
    """
    reported = guard.pack_failures({**COMPLETE, "read": [], "packs": {"subprocess": ["pack.toml"]}})
    assert reported
    assert any("'subprocess' arrived without ['pack.toml']" in line for line in reported)
    assert any("no complete pack arrived" in line for line in reported)


def test_a_complete_directory_the_reader_does_not_admit_is_not_a_carried_pack() -> None:
    """Both halves are required: the files on disk AND the client's own reader.

    They agree today — the reader admits a directory on the strength of its
    manifest, and a complete directory has one — and the step does not assume
    they always will, because the thing being measured is exactly whether what
    the client can read is what the wheel carried.
    """
    assert guard.carried_packs({**COMPLETE, "read": []}) == []
    assert guard.pack_failures({**COMPLETE, "read": []})


def test_a_packs_package_that_could_not_be_read_is_a_failure_not_a_crash() -> None:
    """« The answer could not be obtained » is not « there is nothing wrong »."""
    reported = guard.pack_failures(
        {
            "root": "(could not be read)",
            "entries": [],
            "read": [],
            "packs": {},
            "why": "ModuleNotFoundError",
        }
    )
    assert reported
    assert any("ModuleNotFoundError" in line for line in reported)
