# SPDX-License-Identifier: Apache-2.0
"""The contract's words this client still spells itself, held to where they are published.

Most of the contract's vocabulary is imported: a problem's class, a decision's
outcome, a chain's condition. Two values are not published as names a client
can import — the kind of entry that records an effect is one member of a tuple,
and the largest page a read may ask for is a bound in the binding's own
description — so this client spells them once, and these tests fail the day the
contract says something else.
"""

from __future__ import annotations

import pytest
from contract_absence import contract_is_installed, skip_without_the_contract


@pytest.fixture(autouse=True)
def _the_contract(request: pytest.FixtureRequest) -> None:
    if not contract_is_installed():
        skip_without_the_contract(request, "these values are read from the contract")


def test_the_effect_kind_is_one_the_contract_publishes() -> None:
    from sayfirst_contract.evidence import ENTRY_KINDS

    from sayfirst_cli import pages

    assert pages.EFFECT in ENTRY_KINDS


def test_no_read_asks_for_a_page_larger_than_the_binding_serves() -> None:
    from sayfirst_contract.artifacts import load_json

    from sayfirst_cli.instrument import harness

    description = load_json("binding", "http-unix-socket", "openapi.json")
    parameters = description["paths"]["/scopes/{scope}/evidence"]["get"]["parameters"]
    (page_size,) = [item for item in parameters if item["name"] == "page_size"]
    assert page_size["schema"]["maximum"] >= harness.PAGE_SIZE
