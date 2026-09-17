<!-- SPDX-License-Identifier: Apache-2.0 -->
# `sayfirst` command-line interface

The open-source command-line interface of the `sayfirst` control plane: the
product CLI a user installs to connect an existing program to the boundary, to
read what was decided, and to verify it afterwards. [`QUICKSTART.md`](QUICKSTART.md)
installs it beside its daemon and walks one governed decision end to end — every
command on that page was run before it was written down.

Its content arrives as the partition of the private CLI, by copy with a
provenance review, slice by slice. The first slice is here and it runs:
[`docs/PARTITION.md`](docs/PARTITION.md) says what crosses and what is still
open, and [`docs/PROVENANCE.md`](docs/PROVENANCE.md) says what arrived by copy
— today, nothing, and why that is the right answer rather than an omission.

## Three directions

A client of this control plane does **three** things, and this repository ships
all three.

**Before an effect, it asks.** One question — a capability, a scope — put to the
daemon over a socket whose peer it verified, and one answer rendered as it was
given: allow, deny or suspend, and "could not ask" when the daemon could not be
reached. That is `sayfirst ask`, and it is what the first slice implements.

**It puts the boundary in front of somebody else's program.** `sayfirst
instrument run --pack DIR … -- <program>` runs a program with the named effects
asked about first, reversibly and with nothing written anywhere; `sayfirst
instrument verify` runs it again under the interpreter's own audit hook and
proves, from that and the scope's evidence chain alone, that every effect of a
named kind was preceded by a decision; `sayfirst instrument apply` is reserved
for the committed code modification and refuses, saying so. `sayfirst packs
list` prints the convenience packs this distribution ships, one line each with
the path `--pack` accepts, and `sayfirst packs check PATH` reads one the way the
engine will before anything runs with it.
[`docs/PACKS.md`](docs/PACKS.md) is the whole of it.

**Afterwards, it reads and verifies.** Every read *from the daemon* names its
scope explicitly (`--scope`) — the writer's `local` default does not apply. The
two offline checks name a path instead and take no scope at all: `evidence audit
--file` checks one saved bundle and `evidence exports` a directory of them, and
both refuse `--scope`, because the file says which scope it holds. This is a
surface rather than a list, and it grows by slices; what it answers today is
below, and `sayfirst --help` is the claim that is kept in the dispatch itself.

`sayfirst trace` reads back the record of one decision and follows it into the
evidence that holds it: the record itself, and where it sits in the chain,
bounded to the pages the read walks.

`sayfirst explain` reads the reason the control plane gave for a decision — the
rule it applied and the policy version it ran under — in the plane's own words,
adding none of its own.

`sayfirst evidence history` and `sayfirst evidence audit` page through scoped
evidence: `history` renders what each page holds, `audit` puts the served
verdict beside a local check and names a finding wherever the two disagree;
`--file` checks an already-saved bundle offline, without opening a socket.

`sayfirst evidence export` saves a bundle a third party can verify with the
contract distribution alone, offline, no server code and no daemon; `--out`
names where it is saved. A bundle taken while the daemon's current epoch is
still open verifies with coverage `unknown` rather than `complete` — the honest
answer, not a failure. `sayfirst evidence exports` lists and re-verifies every
`*.json` bundle saved in a directory.

`sayfirst approvals show` reads where one suspended wait stands: its state,
when it was asked, when it ends, and — once a person has acted — when and why.
`sayfirst approvals approve` and `sayfirst approvals reject` end that wait
exactly once, an optional `--reason` and all, and render the same record
`show` would: one person's act, and nothing that counts signatures or names a
designation (article 12). These three follow the exit codes below, with no case
of their own: an approval already resolved, asked again, answers
`approval_resolved`, which the registry classifies as a refusal — so it is the
`3` below, like every other refusal, and this client special-cases nothing.

`trace`, `explain` and `evidence history` exit `0` on a read, whatever the
record's own outcome. `evidence audit`, `evidence export` and `evidence exports`
exit with the local check's result instead: `0` when it holds, `6` when it finds
what the plane did not say, `7` when it cannot conclude — which is the ordinary
answer for a bundle taken while the epoch is still open, and why
`sayfirst evidence export && …` is not how to script one. A chain the verifier
could not judge — an entry declaring a recipe this generation holds no reader
for, a range assembled out of order, an instant outside the calendar — is `7`
as well, with the sequence it stopped at: the answer arrived and the check could
not conclude, which is neither a failure to obtain the answer nor a finding
against the chain. Every command that reads from the control plane exits `3`
when the request was refused, `4` when the plane could not be read from or the
answer itself could not be read at all, and `64` on a misused invocation; a
usage error the parser catches exits `2` everywhere.

`sayfirst instrument verify` uses the same two local-check codes for the proof
it makes: `0` only when every point of every designated pack was `governed` and
no effect went unjudged, `6` for an effect no decision preceded — a finding this
client made, never a denial the plane gave — and `7` when the check could not
conclude, which includes a path the run never walked and an effect this proof
could not judge. A run that concluded nothing at all says which of its endings
happened, and answers with that ending's own code: `4` when the chain could not
be read, before the program started or while it ran, and when the verifier never
saw the program's own code start; `64` when the invocation was refused before it
began; `7` when findings arrived and would not read. `sayfirst instrument run`
owns none of these: it passes the governed program's own ending through
untouched, and answers `64` only for mistakes in the invocation. `sayfirst packs
list` exits `64` when a pack this distribution ships will not read — it names it,
prints the rest of the list anyway, and never ends in a traceback.

The operator closed Q-A on 2026-09-05: this repository owed the evidence
surface, and its promise to read and verify became a commitment with a date on
it — kept, as of this slice. [`docs/PARTITION.md`](docs/PARTITION.md) records
the decision; [`docs/EVIDENCE-SURFACE.md`](docs/EVIDENCE-SURFACE.md) records
what shipped and the contract support it used. Export verification uses the
recipe and vectors from the contract distribution, without importing server
code.

None of the three defines control semantics or derives a decision. A client
"explains and invokes" control semantics; it "never defines them, never keeps a
decision past the lifetime the
control plane gave it, and never derives an answer the control plane did not
give" (article 1). Asking, instrumenting and reading are three ways of carrying
an answer someone else made — the third of them, the verifier, reads the
interpreter and the chain and reaches no verdict of its own about policy — and
that is why all three belong to a client.

## The first slice

One command, end to end, against the open control plane's contract
distribution: `sayfirst ask` puts one question to the daemon and renders its
answer.

```console
$ sayfirst ask --capability example.effect --scope local --socket /run/user/1000/sayfirst.sock
verified: true (server_uid 1000, expected 1000)
outcome: allow
reason: policy_allows
capability: example.effect in scope local
decision: decision-1 at 2026-09-04T20:11:45.929523+00:00
policy version: sha256:44d91909ffe6283e67c73bad39d698448aa5e8bbdc1b5aa64a635a604e12f7e1
```

When the daemon cannot be reached, it says that, and it says it as its own
result rather than as a refusal:

```console
$ sayfirst ask --capability example.effect --socket /run/user/1000/absent.sock
verified: false (server_uid not stated, expected not stated)
could not ask: unreachable: [Errno 2] No such file or directory
retryable: true
$ echo $?
4
```

It exits `0` on `allow`, `1` on `deny`, `5` on `suspend`, `3` when the request
was refused and `4` when the control plane could not be asked — because
article 1 requires that "denied" and "could not ask" never read as each other.
There is no `--url` and nothing that takes a token: the boundary says who the
caller is, and it says so from the socket (article 6).

## The gate

`scripts/gate.sh` is the whole gate: format, lint, tests, and the guard that
installs this distribution into an empty environment and reads back everything
that arrived with it. That last one is article 13 made mechanical rather than
promised — and it proves on every run that it can fail, by planting a web
framework into the environment that has just passed and requiring the check to
reject it.

`sayfirst-contract` is on no index, because article 0 forbids publishing
anything until the marks are filed. So the gate is told where a checkout of the
control plane's repository is:

```console
$ SAYFIRST_CONTRACT_SOURCE=../sf-control-plane-lt ./scripts/gate.sh
```

It fails, rather than skipping, when it is not told. A skipped guard is a guard
that cannot fail.

## What binds here

The constitution of the open control plane —
[`CONSTITUTION.md`](https://github.com/fredaime/sayfirst-control-plane/blob/main/CONSTITUTION.md),
in that repository — binds this repository too. Its article 0 says so: it binds
"this repository and every other open repository of the project", and an open
repository adopts it **by pointer, never by copy, because a copy drifts**.

**That pointer became a link in the act that published this repository, and was
not one before.** The open control plane is published as a repository created
fresh (article 0), and until it existed the only URL this document could have
carried was the one repository the project has decided never to publish — a link
that would have resolved for nobody from the first public minute, in the
document a newcomer reads first. `docs/publication-checklist.md` orders the
control plane before this client for that reason, and
`tests/test_pointers_survive_publication.py` still reddens on any reader-facing
link to the repository that is never published — it is what kept the promise
from being made early. The same applies to `TRADEMARKS.md`, which is why this
repository carries one that points rather than one that copies.

The articles this repository will answer to first:

- **article 1** — a client explains and invokes control semantics; it never
  defines them, never keeps a decision past the lifetime it was given, and never
  derives an answer the control plane did not give;
- **article 13** — the client depends on the contract distribution and never on
  the server distribution, so installing it never installs a web framework or a
  database layer;
- **article 14** — nothing here imports, names or is shaped by a private
  product; files that arrive from a private repository arrive by copy with a
  provenance review;
- **article 15** — Apache-2.0, contributions under the Developer Certificate of
  Origin, read on every pull request by
  `scripts/check_developer_certificate_of_origin.py`, which refuses a commit
  carrying no well-formed sign-off and refuses a range it cannot read rather
  than reporting it as passing.

## The name

The product and the command are **`sayfirst`**, decided by the operator on
2026-09-04. Every
distribution the open side publishes takes it as a prefix, the way the retired
placeholder always said they would: this CLI as `sayfirst-cli`, and the plane as
`sayfirst-control-plane` where the plane is named. *Which* distributions this
repository ships is a different question — that is the partition, and it is not
decided.

### Who holds the command — decided, 2026-09-05

This repository claims the distribution `sayfirst-cli`, the import package
`sayfirst_cli` and the console script `sayfirst`. Until 2026-09-05 that was an
assumption, stated as one: the control plane's repository claimed the same three
names for its operator surface, each repository's guard read its own manifest
and passed, and no test anywhere could see the other tree. The operator settled
it on 2026-09-05, and all three names in all three forms belong to the product
command-line interface, which is this repository.

The control plane's repository is giving them up: its operator surface — the
commands that inspect its daemon — takes the daemon's own form of the product
name instead, the conventional Unix shape in which the daemon and the commands
that inspect it share one binary. That change is on a branch there, dated
2026-09-05 and not merged, so until it merges both trees still declare the three
names. Nothing had been published under either claim (article 0), so the
collision was a fact about two source trees and never about an installed
environment. [`docs/PARTITION.md`](docs/PARTITION.md) records
the question and its answer as Q-D.

Deciding the name did **not** unblock publishing on its own. Article 0 forbids
publishing anything under it — no package on an index, no public repository, no
announcement — until three conditions hold together:

1. **the name is decided** — met, 2026-09-04;
2. **the marks are filed** — no file here can read a registry, so this
   repository asserts nothing about it and a session reading this file must not
   read the decided name as evidence of it. The date the filing was made and the
   reference it produced are recorded on `docs/publication-checklist.md`, and
   article 0 puts that act before any public repository of this project;
3. **every occurrence of the placeholder is replaced** — done here; the
   condition is project-wide, and the other repositories' occurrences are not
   this repository's to change.

## What is still not decided

- **The partition.** Which parts of the private CLI cross, and what is renamed
  on the way, is measured privately and executed slice by slice.
  [`docs/PARTITION.md`](docs/PARTITION.md) proposes the open command surface,
  names the three questions it does not close, and says plainly which of its
  lines is a decision and which is a choice it made to keep moving. Two of its
  questions are now answered — Q-D, the name collision, and Q-A, the evidence
  surface — and both stay in the document, marked closed and dated.

## Boundary with the control plane

The control plane's operator surface keeps `status`, `doctor`,
`policy show|history` and `plugins list`, which inspect its daemon's own state.
`systems {register,retire}` also stays there pending its separate question.
The 2026-09-05 decision assigns `trace`, `explain` and
`evidence {audit,history,exports,export}` to this product client: they read the
decisions and evidence the plane supplied. Q-B, Q-C and Q-E remain open; Q-D
was already closed.
