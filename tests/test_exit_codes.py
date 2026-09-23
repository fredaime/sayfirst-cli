# SPDX-License-Identifier: Apache-2.0
"""Article 1's named guard: denied and could-not-ask are held apart, here.

    "The project's client renders 'denied' and 'could not ask' as distinct
    results with distinct exit codes, and a test holds them apart."
                                                — constitution, article 1

The other assertions are what makes that one survive a later slice: every code
is distinct from every other, every outcome the contract defines has one, and
none of them collides with the code `argparse` produces on a usage error it
rejects itself.
"""

from __future__ import annotations

from sayfirst_contract.decisions import Outcome

from sayfirst_cli import exit_codes
from sayfirst_cli.ask import EXIT_BY_OUTCOME


def test_denied_and_could_not_ask_have_distinct_codes() -> None:
    """The article's own sentence, as an assertion."""
    assert exit_codes.EXIT_DENY != exit_codes.EXIT_COULD_NOT_ASK


def test_every_code_means_one_thing() -> None:
    """A code shared by two situations is a distinction the shell cannot see."""
    assert len(set(exit_codes.CODES.values())) == len(exit_codes.CODES)


def test_only_allow_exits_zero() -> None:
    """Article 1: one outcome means "go ahead", and it is the only success."""
    zero = {name for name, code in exit_codes.CODES.items() if code == 0}
    assert zero == {"allow"}


def test_every_outcome_the_contract_defines_has_a_code() -> None:
    """The outcomes are closed at three, and this client renders all three.

    An outcome added to the contract without a code here would fall to the
    fail-closed branch in `ask`, which is correct but silent; this test is what
    makes it loud, at the release that adds it rather than at the first use.
    """
    assert set(EXIT_BY_OUTCOME) == set(Outcome)
    assert len(set(EXIT_BY_OUTCOME.values())) == len(Outcome)


def test_no_outcome_takes_the_code_the_parser_uses() -> None:
    """A mistyped flag must not be readable as an answer."""
    assert exit_codes.EXIT_PARSER_USAGE not in set(EXIT_BY_OUTCOME.values())


def test_the_codes_the_contract_already_published_are_not_renumbered() -> None:
    """Article 13: one contract, one rendering.

    `sayfirstd whoami` — implemented in the contract distribution — already
    publishes these three codes for these three situations. A second client of
    the same contract that numbered them differently would make one event read
    two ways depending on which subcommand produced it.
    """
    from sayfirst_contract.transport import cli as whoami_cli

    assert exit_codes.EXIT_ALLOW == whoami_cli.EXIT_OK
    assert exit_codes.EXIT_REFUSED == whoami_cli.EXIT_REFUSED
    assert exit_codes.EXIT_COULD_NOT_ASK == whoami_cli.EXIT_COULD_NOT_ASK
    assert exit_codes.EXIT_MISUSE == whoami_cli.EXIT_MISUSE
