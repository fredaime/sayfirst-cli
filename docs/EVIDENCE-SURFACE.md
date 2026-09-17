<!-- SPDX-License-Identifier: Apache-2.0 -->
# Evidence surface — next slice, 2026-09-05

**Shipped 2026-09-15.** [Q-A](PARTITION.md) assigns `sayfirst trace`,
`sayfirst explain` and `sayfirst evidence {audit,history,exports,export}` to
this client. `ask` was the first slice; these four commands are the next, and
this note now records what shipped rather than proposing it — without deciding
Q-B, Q-C or Q-E or reopening Q-D.

**Contract reads.** Use the contract distribution's declared operations and
socket binding, with verified peer identity and negotiated generation. Every
read requires an explicit scope; the writer's `local` default does not apply.

| Command | Contract operation | Returned document |
|---|---|---|
| `trace`, `explain` | `read_decision(scope, decision_ref)` | `decision-record` |
| `evidence audit`, `evidence history` | `read_evidence(scope, from_sequence, page_size)` | `evidence-page-result` |
| `evidence export` | `export_evidence(scope, from_sequence, to_sequence)` | `evidence-export-result` |
| `evidence exports` | local listing of saved bundles; no operation | — |

Renderings: `trace` shows the decision record and follows references through
scoped evidence reads; `explain` shows the supplied reason and policy version.
`history` pages records; `audit` presents the served verification. The read
follows `next_from`, retains scope and range, and exposes declared drops and
partial coverage. Contract problems, missing records, connection failures and
unknown values are rendered explicitly; none means a denial or a clean chain.

**Client verification.** Articles 10 and 13 require an export a third party can
check. Local verification checks document consistency using the versioned
canonicalization, entry preimage, chain and manifest recipe and test vectors
from the **contract distribution**. It runs without server code, server
imports or a running daemon (article 14 also holds the dependency boundary).
It checks entry hashes, predecessor links, sequence gaps and dropped markers,
and the manifest binding to scope, range, contract version, served verdict and
entry hashes. A bounded export proves nothing about records outside its range.

The plane's `verification` and recorded grades are displayed unchanged. Local
check results are labelled separately: a mismatch is a finding, never a
replacement verdict. An unavailable recipe, unknown version or insufficient
coverage cannot become success. A matching digest does not establish
authenticity or upgrade the recorded integrity grade. The gate exercises the
contract's published valid, partial-range and broken/gapped-chain vectors
with the contract distribution installed and no code of the control plane
(`tests/test_offline_audit_vectors.py`); the dependency-closure guard, which
does build a clean installation, does not run them.

**Forbidden.** Never derive a decision, reason or verdict the plane did not
give, recompute its integrity grade, or cache a decision past its assigned
lifetime. Historical records may be read and saved as evidence; they never
authorize a later effect. Never reconstruct minimized payloads, repair the
chain, or invent a disclosure register (articles 1, 7, 10 and 11).

**What a bundle can prove, and when.** The verifier's coverage is `complete`
only when every asynchronous entry in the bundle lies inside a recovery epoch
the daemon closed with a `clean_stop`. An export of a daemon's still-open epoch
therefore verifies with `coverage: unknown`, and `evidence audit --file` exits
`7` (« could not check ») even when its chain is intact and its manifest
recomputes — that is the honest answer to a question the daemon has not yet
closed, not a failure of the check. A bundle taken after a clean stop and
restart can verify `complete`.

Measured 2026-09-15 against a real daemon: an export of a running epoch —
open, or bounded at its head — reads `overall: unverifiable`,
`coverage: unknown`, issues `['coverage_unknown']`, chain `intact`, manifest
recomputes. After `SIGTERM` and a restart, the chain holds
`recovery: clean_stop` covering sequences 1–5; an export bounded `--to 5`
carries that marker as `recovery_context` and verifies `overall: confirmed`,
`coverage: complete`, no issues, the decision confirmed.

The rule is the verifier's H2 (`sayfirst_contract.evidence`, coverage) and the
daemon's V3 (`evidence_reads._recovery_context`: « no marker within the bound
means no context, and the coverage is honestly unknown »).

**How the open questions were closed (2026-09-15).**

1. **Recipe and vectors:** the recipe and vectors were already published by the
   contract distribution (`sayfirst_contract.evidence`, `evidence-preimage-v1.json`,
   `evidence-export-manifest-vectors.json`); the client uses them and publishes
   nothing of its own.
2. **Transport and scenarios:** the three reads — `read_decision`,
   `read_evidence`, `export_evidence` — and `read_policy_status` were added to
   the transport wrapper and the binding client in the control plane
   repository, generation negotiation and peer verification unchanged.
3. **`exports`:** `evidence export --scope S --from N [--to M] --out FILE`
   refuses to overwrite, saves the served bundle, then checks it locally with
   the contract's verifier — exit is the local check's 0/6/7. A bundle whose
   chain the verifier could not judge is `unverifiable`, which is the 7 of that
   same table: the verdict is rendered beside the saved path rather than
   reported as an inability, because what a bundle's content says about its
   chain is a verdict and never an exception. `evidence exports DIR` is a LOCAL
   listing of every `*.json` in a directory, each re-verified: any 6 → 6, else
   any 7 → 7, else 0, with « not a bundle » for a file that is not one and
   « could not check » for a file that could not be read at all; nothing is
   dropped silently. No listing operation exists on the contract, and none is
   invented.
4. **Rendering and exit codes:** the exit codes are 0 read/verified, 3 refused,
   4 could not ask/read, 6 check failed, 7 could not check, 64 misuse, and 2 is
   argparse's, reserved. `trace`/`explain` exit 0 on a read whatever the
   record's outcome; `audit`/`history` are distinct from `export`/`exports` as
   implemented. Machine output is the `ask` envelope with `result`.
5. **Dispatch:** Q-C stays open; the reads dispatch from `main.py` exactly as
   `ask` does, and decide nothing about `whoami`.
