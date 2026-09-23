<!-- SPDX-License-Identifier: Apache-2.0 -->
# The partition of the command surface — proposal, 2026-09-04

**Status: a proposal, with three decisions inside it** — the topology of
2026-09-04, and Q-A and Q-D of 2026-09-05 — each attributed and dated where it
lands. The rest is either read off a measured partition that is itself **not
merged** in the repository that holds it, or a choice this document makes and
marks as its own. Nothing here is settled by being written here. Where a line
can be reversed, it says by what.

This is the record of *what crosses*: which commands the open product client
answers, which live with the daemon in the control plane's repository, which
never become open at all, and which are renamed on the way. It is a document of
this repository rather than of a report, because the answer is needed every time
a slice lands and a report is read once.

## Why this document does not name the private side

Article 14: "Nothing in this repository imports, names, links to or is shaped by
a private product: no private symbol, path, vocabulary or roadmap appears here."
A partition read backwards is a map of what stays private — its modules, its
vocabulary, its schedule — so a file that named the private command tree
alongside the open one would publish exactly what the article forbids, and it
would do so in the repository whose whole job is to hold the line.

So this document names the **open** surface: the command as a user will type it,
where it lives, what decides it, and what is still open. The mapping to the
private tree — module by module, with the line counts and the old names — is
part of the provenance record article 14 keeps **private**, and it stays there.
That is not a gap in this document; it is the article applied to it.

## What decides a line

Five questions, asked in this order; the first that answers, decides.

1. Does the command's subject exist because there are several hosts, several
   organisations, or a regulatory obligation? Then it is not the open control
   plane's business at all, and it does not cross — **article 1**.
2. Does it *inspect the daemon* — what the daemon's status is, whose identity it
   saw, which plugins it composed, which scenarios it replays? Then it lives
   with the daemon, in the control plane's repository — **operator decision of
   2026-09-04**, applying article 14. **Narrowed by the operator on
   2026-09-05**: the subject of this question is the daemon's *own state*.
   Reading the evidence a daemon wrote is not inspecting the daemon — the chain
   outlives the process that wrote it, and article 10 puts it in the open core
   for a reader rather than for an operator — so the reads fall through to
   question 3 and are a client's. Q-A below is that decision in full.
3. Does it read or verify an answer or evidence the plane supplied, work in the
   user's own repository, or point the user's own program at the boundary? Then
   it is a client command and it lives here — **articles 1, 10, 13 and 14**.
4. Does its name or its options name a particular vendor, framework, model or
   tool? Then the mechanism crosses and the name does not — **article 4**.
5. Otherwise it crosses here, and its name and its help text are written for a
   reader who has never heard of any private product — **article 14**.

And one rule that is not a question: **nothing crosses without its guard**. A
command copied without the test that proves its property has not travelled; it
has been moved.

## The open command surface

`sayfirst` is one command with subcommands. "Here" is this repository, the one
that declares the `sayfirst-cli` distribution and installs the console script;
"daemon" is the control plane's repository, which keeps the operator surface
that inspects its own daemon.
`systems {register,retire}` stays there pending its separate question.

| Command | Lives | State | What decides it |
|---|---|---|---|
| `ask` | here | **running** — the first slice | Article 1. One question, one answer, three outcomes, an exit code each. **New code**: it exists in no tree today, and §"Why the first slice is new code" below says why that matters. |
| `connect` | here | crosses, amputated | Article 6. A profile becomes a socket path, a mode, and the account the daemon runs as. Everything that named a URL or carried a token is cut, not renamed: there is nothing left for it to address. |
| `whoami` | here **and** daemon | crosses, and is already answered | Article 6 names it. The contract distribution implements it and the daemon's own command forwards it; a client that asks it over its own verified connection is the same operation, not a second one. **Open**: whether this repository answers it or forwards it. |
| `profile` | here | crosses, amputated | Article 6. Listing, choosing and showing profiles; no credential store, because there is no credential. |
| `approvals` | here | crosses, amputated — **running**, shipped 2026-09-16 | Article 12. Read a suspended request, approve it, reject it — one person, and nothing that counts signatures or names a designation. |
| `integrate` | here | crosses, renamed | Articles 4 and 9. Plan, apply, verify and roll back an integration inside the user's own repository. The option that named one vendor's tool becomes an option that names **any** command to run; the mechanism is generic, the named performer never was. |
| `packs` | here | crosses, renamed | Article 9. Declaring, pinning and verifying the packages a program integrates with is a client's act, done in the client's repository. The word is the open one; the private word does not appear here. |
| `instrument {run,verify,apply}` | here | **`run` and `verify` running — shipped 2026-09-15**; `apply` present and refusing | Article 9: the open project ships the instrumentation engine, its verifier and the convenience packs. Question 3 above names the act in its own words — it "point[s] the user's own program at the boundary" — so this is a client command and lives here. The three verbs are the architecture reading of 2026-09-14: `run` is the reversible, process-scoped primary mode; `verify` is the proof — layer 3, shipped 2026-09-15: it runs the program in a subprocess under the interpreter's own audit hook and establishes, from those events and the daemon's evidence chain alone, that every effect of a named kind was preceded by a decision (`docs/PACKS.md` § Verifying); `apply` keeps the article's name for the committed code modification and refuses, with its reason, until that mode exists. **Added 2026-09-15**: this row did not exist while the command did not, and the guard `tests/test_partition_boundary.py` now reads the same line — verb by verb, since a row that said a running verb refuses is the defect this one was. |
| `trace` | here | **running** — shipped 2026-09-15 | Article 1. It reads back the record of a decision the control plane made and renders it; a client "explains and invokes" what it "never defines" and "never derives", and reading an answer it did not derive is the article's own description of a client. |
| `explain` | here | **running** — shipped 2026-09-15 | Article 1, the same sentence read the other way. It renders the reason the control plane gave for a decision and adds none. A command that composed a reason of its own would be "a second control plane without evidence", which is the article's stated reason for the rule. |
| `evidence {audit,history,exports,export}` | here | **running** — shipped 2026-09-15 | Articles 10 and 13. Article 10: "the evidence chain, its verification verdict and raw export belong to the open core" — they are published to be read, and the reader is a client. Article 13: third-party implementability "is the purpose of publishing" the contract, so verifying an export must be possible from the contract distribution alone, with no server code installed. |
| `version` | here | crosses, renamed | Article 0. It names the distributions it reports, and every one of those names changes with the decided name. **Choice**: it crosses, because a client that cannot say which contract generation it speaks cannot be debugged. |
| `status` | daemon | does not come here | Article 7 and the operator decision. It must show the integrity grade, and it reads that from the daemon it inspects. The client does not lose the grade by not having this command: article 7 puts the grade in **every verdict**, so a client that wants it reads the field it was given, and never computes a second one. |
| `doctor` | daemon | does not come here | Article 2 and the operator decision. It diagnoses the daemon. |
| `plugins list` | daemon | already there | Article 8. It reports what the daemon discovered and composed. |
| `conformance replay` | daemon | already there | Article 13. It replays the published scenarios against a daemon. |
| `policy show\|history` | daemon | does not come here | The operator decision of 2026-09-04, question 2 above. It reports which policy *this daemon* loaded and which versions it has run under: the daemon's own state, read from the daemon, and unreadable when the daemon is not there. |
| `systems {register,retire}` | daemon | stays, under its own question | Untouched by the decision of 2026-09-05, which named the evidence surface and nothing else. The measured partition already marked this line for a second look — registering a host is not obviously an act *on* this host, and article 1 draws its line between one host and many — and it stays with the daemon until that question is asked and answered, rather than moving as a side effect of another one. |
| The commands that inspect the daemon | daemon | do not come here | Article 1 and the operator decision of 2026-09-04, **narrowed on 2026-09-05**: what travels with the daemon is what reads *the daemon's own state*. Reading the evidence the daemon wrote is not that, and does not travel with it: `trace`, `explain` and `evidence` are the three families that moved, and they have rows of their own above. |
| Repository discovery | **open — see below** | contested | It reads a path in the user's own repository and never opens the daemon's socket, yet the measured partition groups it with the commands that inspect the daemon. This is the one line where this document says the measurement is wrong. |
| Everything whose subject is several hosts, several organisations, or a regulatory obligation | nowhere open | does not cross | Article 1, verbatim: those are "the business of products built on top of it, which depend on it and never the reverse." They are not named here, because naming them is the map article 14 forbids. |

## Why the first slice is new code and not a copy

The provenance review article 14 requires has one question open that engineering
cannot answer and no guard can close: what the authorship of the commits in a
private history implies, in law, for the copyright of files copied out of it.
The measured partition marks that question **blocking for the first copy into an
open repository**, and its owner is counsel, not this session.

So the first slice was **written**, not copied. `docs/PROVENANCE.md` records that
its provenance table is empty and why an empty table is the correct answer today
rather than an oversight. This is not a workaround: a walking skeleton was
always going to contain code that exists in no tree — the socket transport and
the identity established from a peer credential do not exist on the private side
to be copied — and starting with that part is the ordering that does not wait.

## The open questions this document does not close

Named as open, rather than quietly decided. Two of them have since been closed
by the operator; they stay here, marked closed and dated, because a question
deleted on the day it is answered leaves a document that never had it.

**Q-A — Does reading a decision afterwards belong to the client? Closed,
2026-09-05.**
This repository's README promised a product CLI a user installs "to read what
was decided, and to verify it afterwards", while the operator decision of
2026-09-04 left the commands that read the daemon's records with the daemon.
Both could not be true as written, and the two readings were not equivalent:
one gives the product client an evidence surface, the other makes evidence an
operator-only act on the host.

*Decided by the operator, 2026-09-05:*

> the open product client must not be an asking client only; it interacts both
> ways. The evidence surface **crosses** into this repository.

Concretely: `trace`, `explain` and `evidence {audit,history,exports,export}`
move from **plane** to this repository, and the table above now says so with
the article that carries each. The control plane's operator surface keeps what
inspects its own daemon — `status`, `doctor`, `policy show|history`,
`plugins list` — and `systems {register,retire}` stays with it under its own
question. (What it implements today is `sayfirstd status`, `whoami`,
`plugins list` and `conformance replay`; the decision placed the others, it
did not ship them.) The decision narrows question 2 rather than overturning it: what
travels with the daemon is what reads the daemon's *own state*, and evidence
outlives the process that wrote it.

**The consequence, stated so that it cannot be read as costless.** This
repository now **owes an evidence surface**. Three command families are named
here and, when this was decided, none of them existed: the `here` column was a
debt, not an inventory. (All three shipped on 2026-09-15; the table above marks
them running.) The README's promise stops being an aspiration and becomes a
commitment with a date on it — a sentence that can now be tested against this
repository rather than argued about. It also puts an article 13 obligation on
this repository specifically: verifying an export must be possible with the
contract distribution installed and no server code, because third-party
implementability "is the purpose of publishing" the contract, and a client that
had to import the server to check a chain would have disproved the article by
being the first reader to fail it. `docs/EVIDENCE-SURFACE.md` is the design note
for that slice, and it records what the contract does not yet ship for it.

**Q-B — Repository discovery is placed by its name, not by what it does.**
It opens no socket, holds no profile and reads a path the user gives it, exactly
as the pack and integration commands do. The measured partition counts it with
the operator surface. *This document's position:* it is a client command and
belongs here — a **choice**, marked as one, and the evidence for it is in the
private provenance record where the module can be named. *What reverses it:*
the operator saying the grouping was intended.

**Q-C — Who answers `whoami`?**
Article 6 names it once; two distributions can answer it. Forwarding keeps one
implementation; answering it here keeps the client's connection and its
rendering in one place. *What settles it:* not Q-D, which closed on 2026-09-05
without touching this — deciding who owns the name did not decide which
distribution answers the subcommand. The control plane's operator surface
forwards it to the contract distribution today; this repository forwards
nothing, and either answer is still open to it. *Meanwhile:* the first slice
answers neither and does not need to.

**Q-D — Two repositories claimed the same three names. Closed, 2026-09-05.**
The distribution `sayfirst-cli`, the import package `sayfirst_cli` and the
console script `sayfirst` were claimed in this tree and in the control plane's
tree at once. Each repository's own guard read its own manifest and passed;
neither could see the other, so **no test in either repository caught it**.
Nothing was published (article 0), so the collision was a fact about two source
trees and not about any installed environment — but two wheels that both ship
`sayfirst_cli` cannot be installed together.
*Decided by the operator, 2026-09-05:* all three names, in all three forms,
belong to the product command-line interface, which is this repository. The
control plane's repository keeps its operator surface and renames it to the
daemon's own form of the product name — the conventional Unix shape, where the
daemon and the commands that inspect it share one binary. That change merged the
same day (the control plane's operator command is `sayfirstd`), and only this
repository declares the three names. This document's earlier position was an **assumption**, stated so
it would be visible; it is now the decision, and it changes nothing in this tree
because the assumption and the decision agree.

**Q-E — A command that acts on the daemon rather than inspecting it.**
The operator decision names *inspection*. A command that stops the daemon acts.
The measured partition places it with the operator surface and marks the line as
its own choice. This document does not disturb that, and repeats that it is a
choice: separating the act from the surface that shows it would put the act and
its observation in two products.

## How much of this is settled

- **Settled by the operator, 2026-09-04:** that this repository receives the
  client's partition, and that the control plane's repository keeps only the
  operator surface that inspects its daemon. That single decision fixes the
  `here` / `daemon` column for every command whose placement turns on it.
- **Settled by the operator, 2026-09-05:** Q-A. The evidence surface crosses:
  `trace`, `explain` and `evidence {audit,history,exports,export}` are this
  repository's, the control plane keeps the surface that inspects its own
  daemon, and this repository owes the three families it now claims.
- **Settled by the operator, 2026-09-05:** Q-D. The distribution `sayfirst-cli`,
  the import package `sayfirst_cli` and the console script `sayfirst` are this
  repository's, and the control plane's operator surface is renamed. Q-C, which
  said it would be settled by "the same decision that settles the console
  script", is *not* settled by it: that decision says who owns the name, not
  which distribution answers `whoami`, and Q-C stays open below.
- **Settled by the constitution:** the reasons. An article is not a proposal.
- **A proposal:** every remaining line. The measured partition it draws on lives
  on an unmerged branch of the repository that holds it, in two versions that
  differ; it is therefore not that repository's settled position either, and
  this document is no stronger than its source.
- **A choice of this document, marked as one:** the placement of repository
  discovery, and the crossing of the version command.
- **Open:** Q-B, Q-C and Q-E above. Q-A and Q-D are closed, both on 2026-09-05.
