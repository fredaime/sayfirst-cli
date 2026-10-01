# SPDX-License-Identifier: Apache-2.0
"""The umbrella pins its three owners to its own version, which is the client's.

`sayfirst` depends on three distributions and installs nothing of its own, so its pins
ARE the distribution. A pin left behind by a version bump would publish an
umbrella that installs last release's product under this release's number, and
a range in place of a pin would install whatever the index held that day.

The rule is `pin_failures` in `scripts/check_umbrella_install.py`, which the
gate runs before it installs anything; this file reads the same function and
plants the defects against it.

It needs no contract package, so it speaks in a reduced run too.
"""

from __future__ import annotations

from pathlib import Path

import check_umbrella_install as guard

REPOSITORY = Path(__file__).resolve().parents[1]


def _tables() -> tuple[dict[str, object], dict[str, object]]:
    return guard.project_table(guard.UMBRELLA), guard.project_table(REPOSITORY)


def _dependencies(umbrella: dict[str, object]) -> list[str]:
    found = umbrella["dependencies"]
    assert isinstance(found, list)
    # Anti-vacuity floor: three pins, or the rule below is about nothing.
    assert len(found) == 3, found
    return [str(item) for item in found]


def test_the_umbrella_pins_its_three_owners_to_the_clients_version() -> None:
    umbrella, client = _tables()
    assert guard.pin_failures(umbrella, client) == []


def test_a_pin_left_behind_by_a_version_bump_is_caught() -> None:
    """WATCHED FIRING. The client moved and one pin of the umbrella did not."""
    umbrella, client = _tables()
    stale = [
        "sayfirst-cli==0.0.1" if item.startswith("sayfirst-cli==") else item
        for item in _dependencies(umbrella)
    ]
    reported = guard.pin_failures({**umbrella, "dependencies": stale}, client)
    assert len(reported) == 1
    assert "sayfirst-cli==0.0.1" in reported[0]
    assert f"sayfirst-cli=={client['version']}" in reported[0]


def test_a_range_in_place_of_a_pin_is_caught() -> None:
    """WATCHED FIRING. `>=` installs whatever the index holds that day."""
    umbrella, client = _tables()
    ranged = [item.replace("==", ">=") for item in _dependencies(umbrella)]
    reported = guard.pin_failures({**umbrella, "dependencies": ranged}, client)
    assert len(reported) == 1
    assert f"sayfirstd>={client['version']}" in reported[0]


def test_a_fourth_dependency_is_caught() -> None:
    """WATCHED FIRING. The product is three owners; a fourth name is a different product."""
    umbrella, client = _tables()
    more = [*_dependencies(umbrella), "requests==2.32.0"]
    reported = guard.pin_failures({**umbrella, "dependencies": more}, client)
    assert len(reported) == 1
    assert "requests==2.32.0" in reported[0]


def test_an_extra_is_a_fourth_dependency_by_another_door() -> None:
    """WATCHED FIRING. `sayfirst[web]` would install what the product does not name."""
    umbrella, client = _tables()
    extra = {**umbrella, "optional-dependencies": {"web": ["starlette"]}}
    assert guard.pin_failures(extra, client) == [
        "the umbrella declares extras ['web']: "
        "the product is three pins, and an extra is a fourth dependency by another door"
    ]


def test_an_umbrella_at_another_version_than_the_client_is_caught() -> None:
    """WATCHED FIRING on the first half of the rule: both lines speak, each of its own half."""
    umbrella, client = _tables()
    reported = guard.pin_failures({**umbrella, "version": "9.9.9"}, client)
    assert reported == [
        f"the umbrella carries 9.9.9 and the client {client['version']}: "
        f"one repository releases one version"
    ]


def test_an_umbrella_with_no_dependencies_at_all_is_caught() -> None:
    """WATCHED FIRING. A missing table is a failure, never a crash and never a pass."""
    umbrella, client = _tables()
    without = {key: value for key, value in umbrella.items() if key != "dependencies"}
    reported = guard.pin_failures(without, client)
    assert len(reported) == 1
    assert reported[0].startswith("the umbrella depends on [] and the rule is exactly ")
