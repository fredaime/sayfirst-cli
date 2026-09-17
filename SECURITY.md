<!-- SPDX-License-Identifier: Apache-2.0 -->
# Security

This is the product command-line interface of the `sayfirst` control plane. The
constitution of that control plane binds this repository too — it says so in
article 0, and an open repository adopts it by pointer rather than by copy. Where
this document and the constitution disagree, the constitution wins and the
disagreement is a defect to record.

## What this software is, and is not

This is a **client**. It asks a control plane a question and renders the answer;
it decides nothing. It "explains and invokes" control semantics and "never
defines them, never keeps a decision past the lifetime the control plane gave
it, and never derives an answer the control plane did not give" (article 1).

That matters for a threat model in a specific way: **there is no policy in this
program to subvert.** A defect here cannot make a denied effect allowed. It can
misreport an answer, and the rest of this document is mostly about the ways it
could and what stops them.

What it does **not** do, stated because a governance tool invites the assumption:
it does not confine anything. The control plane it speaks to is a governance and
observability layer, not a confinement mechanism; a program that does not call
the boundary is not governed, and nothing in this repository changes that. Pair
the system with operating-system sandboxing for code you do not trust.

## What it is, today

**Seven commands.** `sayfirst --help` is the claim that is kept in the dispatch
itself rather than here, and this list is what it answers:

- `ask` puts one question — a capability, a scope — to the daemon over a socket
  whose peer it verified, and renders the answer as it was given;
- `trace` and `explain` read back the record of a decision the control plane
  made and the reason it gave, adding none of their own;
- `evidence {history,audit,export,exports}` pages scoped evidence, puts the
  served verdict beside a local check, saves a bundle a third party can verify
  offline, and re-checks saved ones;
- `approvals {show,approve,reject}` reads where one suspended wait stands and
  ends it exactly once;
- `instrument {run,verify}` puts the boundary in front of somebody else's
  program, and then proves — from the interpreter's own audit hook and the
  scope's evidence chain alone — that every effect of a named kind was preceded
  by a decision. `instrument apply` is reserved for the committed code
  modification and refuses, saying so;
- `packs {list,check}` lists the convenience packs this distribution ships and
  reads one the way the engine will before anything runs with it.

What is **not** here is named too, because a security document that let a reader
assume a surface would be the overclaim article 2 forbids, in the file a reader
checks first: `connect`, `profile`, `whoami`, `integrate` and `version` are
named in `docs/PARTITION.md` and none of them exists in this distribution.

**One of those surfaces can fail open, and it is the one this program measures.**
`instrument run` interposes on named effects; an effect it does not reach runs
unasked, which is not a denial overridden but a decision never taken. That is
why `instrument verify` is a separate act rather than a promise made by `run`:
it re-runs the program under the interpreter's own audit hook, and an effect no
decision preceded is reported as this client's own finding — exit `6` — never as
a verdict the plane gave. A check that could not conclude answers `7`. Neither
answer is ever `0`.

## Identity, and the absence of credentials

**There is nothing here to steal.** This client holds no token, no session, no
key, and no credential store. It takes no `--url`. Identity is the operating
system's: the daemon listens on a Unix domain socket and only there, and it
learns who is calling from the peer credential the kernel reports at `accept()`
(article 6). A remote operator reaches a daemon through that socket forwarded
over SSH, carrying their own identity — the control plane never authenticates a
network peer, and this client never presents one.

So the usual client-side compromises do not apply: there is no credential to
exfiltrate from a config file, none to leak into a process listing, and none to
rotate after an incident.

What replaces them is the socket's permissions and the connection's verification.
`sayfirst ask` reports what it verified, on every answer:

```console
verified: true (server_uid 1000, expected 1000)
```

A connection it could not verify is reported as unverified rather than silently
trusted.

## Three outcomes, and a fourth thing that is not an outcome

The control plane answers **allow**, **deny** or **suspend**, and that set is
closed (article 1). When the daemon cannot be reached at all, that is **not** a
fourth outcome and must never be rendered as one:

```console
could not ask: unreachable: [Errno 2] No such file or directory
retryable: true
$ echo $?
4
```

`allow` exits 0, `deny` exits 1, `suspend` exits 5, a refused request exits 3,
and **"could not ask" exits 4** — a separate code from `deny`, because "denied"
and "could not ask" must never read as each other. A caller that branched on a
single non-zero exit would treat an unreachable daemon as a refusal; the codes
exist so that it cannot.

An outcome in a vocabulary this client does not recognise is reported as unknown
and stops the effect as "could not ask" does — never as a denial (article 13).

## What it depends on, and what that excludes

This client depends on the contract distribution and **never on the server
distribution** (articles 13 and 14). Installing it therefore never installs a web
framework or a database layer — the attack surface a client drags in is the thing
that rule exists to bound.

That is measured rather than promised: `scripts/check_dependency_closure.py`
installs this distribution into an empty environment and reads back everything
that arrived with it. It proves on every run that it can fail, by planting a web
framework into an environment that has just passed and requiring the check to
reject it. A guard that cannot be shown to fail is not evidence.

## What is not yet proven

Stated plainly rather than left for a reader to discover.

- **A bundle taken while the daemon's epoch is still open proves less than a
  closed one.** Export verification is implemented — from the contract
  distribution's own canonicalization, recipe and test vectors, with no server
  code and no running daemon, which is what article 13 asks for — but its
  coverage is `complete` only for entries inside an epoch the daemon closed. An
  export of a still-open epoch verifies with coverage `unknown`, and
  `evidence audit --file` exits `7`, « could not check », even when its chain is
  intact and its manifest recomputes. `docs/EVIDENCE-SURFACE.md` is the whole of
  it.
- **`instrument verify` proves the path it walked and nothing about a path it did
  not.** An effect that never ran is not an effect that was governed. The check
  says which of its endings happened and answers `7` rather than `0` whenever it
  could not conclude, including for a path the run never reached.
- **No release has been published.** The one act that publishes a distribution is
  the operator's tag — `docs/publication-checklist.md` says so, and the release
  workflow starts on no other event — and none has been cut. So there is no
  distribution on any index to audit or pin, and no signature scheme to describe
  yet; `CHANGELOG.md` is where the first one is named.

## Publication

This repository was created **fresh** — article 0's first path — and its first commit is the
reviewed tree: no history, no branch, no tag, no issue and no pull request was carried across,
because every one of those becomes public with a repository whose visibility is flipped instead.
The repository the tree was reviewed in is not this one; its visibility was never changed, and it
is kept there as the record of how this one was built.

GitHub's **private vulnerability reporting** is enabled here in the same act that created the
repository (article 0), so that the channel named below exists from the first public minute — the
hosting platform permits that setting on a public repository only. Both acts are lines of
`docs/publication-checklist.md`, which is where the date and the reference each one produced are
recorded.

## Reporting a vulnerability

Do not open a public issue.

Use GitHub's **private vulnerability reporting** on this repository: Security →
Report a vulnerability. It is enabled here from the first public minute (above),
and only this repository's administrators and security managers see such a
report. There is no address to write to instead, and that is deliberate: one
channel is one place a report cannot arrive at unread.

We aim to acknowledge within seven days. Coordinated disclosure applies, with a
ninety-day default that can be shortened by agreement or extended when a fix
needs it. Reporters are credited unless they prefer not to be.

If a report concerns the control plane rather than this client, it belongs in
that repository's channel; if you are unsure which, send it here and we will
route it rather than ask you to judge.
