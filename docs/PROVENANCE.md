<!-- SPDX-License-Identifier: Apache-2.0 -->
# Provenance of the files in this repository

Article 14: "Files that enter an open repository from a private one enter by
copy, each with a provenance review that records the copyright holder of every
file copied, never by history rewriting; `NOTICE` names every holder."

This file is the open half of that record. It carries, for every file that
arrived **by copy**, the copyright holder and the licence — and nothing else.
The review itself — which file, from which commit, read by whom, and what was
cut on the way — is the private half, and article 14 keeps it private: "its
record is private, and the pull request that makes the copy carries the
copyright holder and the licence, nothing more."

## Files that arrived by copy

**None.** The table is empty, and that is the answer rather than an omission.

| File | Copyright holder | Licence | What changed on the way |
|---|---|---|---|
| *(no file in this repository arrived by copy)* | — | — | — |

Two reasons, and the first is the binding one.

**A copy is blocked, and not by engineering.** The provenance review has one
question open that no measurement, no guard and no count of commits can answer:
what the authorship recorded in a private history implies, in law, for the
copyright of files copied out of it. The owner of that question is counsel, and
it is marked as blocking the **first** copy into an open repository — before it,
not in parallel with it, because a copy published under a false provenance is
not withdrawn by reverting a commit. Until it is answered, the honest number of
copied files in this repository is zero, and a table that showed one would be
the claim article 2 forbids: stronger than the evidence held for it.

**The first slice did not need one.** A walking skeleton was always going to be
written rather than extracted. The transport this client speaks — a Unix socket,
with the identity established from the peer credential the kernel reports and
the server verified before a byte is written — exists in no private tree to be
copied; it is new code by necessity, not by preference. Starting the open
repository with the part that has no provenance question is the ordering that
does not wait for one.

## Files this repository authored

Everything else here was written in this repository. Under article 15 each one
carries its SPDX identifier in its own bytes, and `tests/test_spdx_identifiers.py`
fails if one does not.

| Path | Licence | What it is |
|---|---|---|
| `src/sayfirst_cli/` | Apache-2.0 | The command tree, the `ask` command, the exit codes and the rendering. |
| `tests/` | Apache-2.0 | The guards, and the test double that answers what the contract's own fake will not. |
| `scripts/` | Apache-2.0 | The gate, and the dependency-closure guard it runs. |
| `docs/` | Apache-2.0 | This file and `PARTITION.md`. |
| `pyproject.toml` | Apache-2.0 | The distribution, its one dependency, and the console script. |
| `LICENSE`, `NOTICE` | — | Notices rather than works; article 15 excepts them from the header rule by name. |

## What a copy must satisfy before it is added here

Recorded now, so that the first copy does not have to rediscover it.

1. **The blocking question is answered.** Counsel's answer, not an engineer's
   recommendation, and recorded before the pull request is opened.
2. **The file names nothing private.** A copy that imports, names or is shaped
   by a private product does not cross: it is rewritten, or it is left where it
   is. A comment that anchors a rule to a private incident, a private ticket or
   a private table is the rule restated without its anchor, or it is deleted.
3. **The row is added here**, with the copyright holder and the licence, and
   nothing more. No source path, no commit of a private repository, no module of
   origin, no sentence beginning "extracted from".
4. **`NOTICE` names the holder.** If a copy ever brings a second copyright
   holder, `NOTICE` gains a line in the same change.
5. **Its guard arrives with it.** A file copied without the test that proves the
   property it exists to hold has not travelled; it has been moved.

## The holder

`NOTICE` names one holder: Frédéric Aime, acting in a personal capacity, because
the entity intended to hold these rights does not exist yet. On the day it does,
`NOTICE` and the row template above change in the same act.
