# SPDX-License-Identifier: Apache-2.0
"""One process exit code per thing that can come back, all of them distinct.

Article 1 names this file's guard: "The project's client renders 'denied' and
'could not ask' as distinct results with distinct exit codes, and a test holds
them apart." Article 2 is why the list is longer than two: an answer, a refusal
of the question and an unanswerable question are three different facts, and a
shell that collapses them into "non-zero" has lost the one distinction the
constitution insists on.

Three of these codes are not this repository's to choose. `sayfirst whoami`,
which the contract distribution implements, already publishes `0`, `3`, `4` and
`64` for the same four situations; a second client of the same contract that
numbered them differently would make the same event read two ways depending on
which subcommand produced it. So they are taken as given; the codes for the
three outcomes and the local checks are added here.

Article 1 also keeps a local check apart from an answer. A broken chain or a
contradicted verdict is something this client found, not a denial the plane
gave. A check that cannot conclude is not a failure to ask the plane either:
the record may have arrived, while its version or coverage prevents a check.

`2` is absent on purpose: `argparse` exits with it on a usage error it rejects
itself, before any of this runs. Claiming it for an outcome would make a
mistyped flag indistinguishable from an answer.
"""

from __future__ import annotations

from typing import Final

#: The control plane answered `allow`. The only code that means "go ahead".
EXIT_ALLOW: Final[int] = 0

#: The control plane answered `deny`. An answer, not a failure to obtain one.
EXIT_DENY: Final[int] = 1

#: The request was refused — the question was received and rejected.
#: The value `sayfirst whoami` publishes for the same situation.
EXIT_REFUSED: Final[int] = 3

#: The control plane could not be asked, or answered something this generation
#: cannot read. Never rendered as a denial (articles 1 and 2). The value
#: `sayfirst whoami` publishes for the same situation.
EXIT_COULD_NOT_ASK: Final[int] = 4

#: The control plane answered `suspend`: the effect waits for a person.
EXIT_SUSPEND: Final[int] = 5

# A successful read exits 0 without another zero-valued name in CODES: a read's
# success is not an outcome; the record's own outcome is data, not permission.
#: A local verification found what the plane did not say: a broken chain, an
#: undeclared gap, a manifest that does not recompute, or a served verdict the
#: local check contradicts. A finding, never a denial (article 1).
EXIT_CHECK_FAILED: Final[int] = 6

#: The local check could not conclude: an unknown preimage or manifest version,
#: or insufficient coverage. An unknown check, not an unanswerable question.
EXIT_COULD_NOT_CHECK: Final[int] = 7

#: The invocation was wrong, or something it named cannot be read — a profile
#: that cannot say what it must verify, a pack manifest that does not parse, a
#: pack this distribution ships that will not read. The value `sayfirst whoami`
#: publishes for the same situation; `packs list` uses it for a broken shipped
#: pack rather than minting a code for a case no caller can act on differently,
#: because a distinct number would cost one in a table three commands share and
#: the paragraph above says why the numbers here are not this repository's alone
#: to choose. « The invocation was wrong » is a stretch for a pack the
#: DISTRIBUTION ships, and it is the honest half of the answer: the caller typed
#: nothing wrong, and something the command named cannot be read.
EXIT_MISUSE: Final[int] = 64

#: The code `argparse` uses for a usage error it rejects itself. Reserved
#: rather than assigned, so that nothing here can collide with it.
EXIT_PARSER_USAGE: Final[int] = 2

#: Every code this client can exit with, by the name of what it means.
CODES: Final[dict[str, int]] = {
    "allow": EXIT_ALLOW,
    "deny": EXIT_DENY,
    "refused": EXIT_REFUSED,
    "could_not_ask": EXIT_COULD_NOT_ASK,
    "suspend": EXIT_SUSPEND,
    "check_failed": EXIT_CHECK_FAILED,
    "could_not_check": EXIT_COULD_NOT_CHECK,
    "misuse": EXIT_MISUSE,
    "parser_usage": EXIT_PARSER_USAGE,
}
