<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

Every release of this client carries a section here, named for the version the project file
declares; a release with no section fails the gate.

## Unreleased

- Every commit of a change is read for its sign-off on every pull request, and one that carries
  none is refused by name. A range that cannot be read is refused too, rather than reported as
  passing.
- The publication checklist carries every act the constitution names, in the order they are
  performed, and a guard fails when one of them stops being a line of it. The security policy says
  which of article 0's two paths this repository is published by: a fresh repository, never a
  change of visibility.

## 0.2.0

- The evidence surface reads and verifies: `history` pages a scope, `audit` puts the served
  verdict beside a local check and names a finding wherever the two disagree, `export` saves a
  bundle a third party verifies offline with the contract distribution alone, and `exports`
  checks a directory of saved bundles without opening a socket.
- `instrument run` puts the boundary in front of somebody else's program, reversibly and writing
  nothing; `instrument verify` runs it again under the interpreter's own audit hook and proves,
  from that and the scope's evidence chain alone, that every effect of a named kind was preceded
  by a decision; `instrument apply` is reserved and refuses, saying so.
- `trace` reads back the record of one decision and follows it into the evidence that holds it:
  the record itself, and where it sits in the chain, bounded to the pages the read walks. Like
  every read from a daemon it names its scope explicitly, and it exits `0` on a read whatever the
  decision it read said.
- `explain` renders the reason the control plane gave for a decision — the rule it applied and
  the policy version it ran under — in the plane's own words, and composes none of its own. A
  client explains and invokes control semantics; it never derives them, and a command that
  reasoned here would be a second control plane with no evidence behind it.
- `packs list` prints the convenience packs this distribution ships, one line each with the path
  `--pack` accepts, and `packs check` reads one the way the engine will.
- `approvals` shows a suspended ask and ends the wait, so the next ask runs the body once.
- A verdict the verifier could not reach is rendered as it was given rather than as a negative
  fact about the chain.
- The release itself: this distribution moves to `0.2.0`, and installing it pins
  `sayfirst-contract==0.2.0` and `sayfirst-boundary==0.2.0` — the contract this client speaks and
  the runtime a governed program holds its grant in — at that version and no other. An
  installation of this version therefore carries exactly those two, and upgrading it moves all
  three together.
