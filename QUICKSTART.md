<!-- SPDX-License-Identifier: Apache-2.0 -->
# Quickstart

Everything on this page was run, in this order, on one machine before it was
written down: the commands are pasted from that run, and so are their answers.
Your identifiers, timestamps and hashes will differ; the shapes will not.

## What you need

- Linux or macOS. The control plane listens on a local socket and reads who
  is calling from the kernel; there is no port and nothing that takes a token.
- Python 3.12, 3.13 or 3.14. The walk below used 3.12, the floor.
- [`uv`](https://docs.astral.sh/uv/) to build and install. The walk used 0.12.
- Until the distributions are on an index: a checkout of the control plane's
  repository, <https://github.com/fredaime/sayfirst-control-plane>, beside a
  checkout of this one, <https://github.com/fredaime/sayfirst-cli>. Both are
  read at their default branch.
- A home directory that only you can write. The daemon refuses to put its
  socket under a directory that a group can write and that is not sticky, so a
  run directory under a shared scratch space is refused with
  `socket_directory_unprotected` — the walk below met exactly that once, and
  moved.

## 1. Build the distributions and install them

From a directory of your own — the walk used `~/quickstart`:

```console
$ mkdir -p ~/quickstart/wheels && cd ~/quickstart
$ (cd /path/to/sayfirst-control-plane && uv build --all-packages --out-dir ~/quickstart/wheels)
$ (cd /path/to/sayfirst-cli && uv build --out-dir ~/quickstart/wheels)
$ uv venv --python 3.12 .venv
$ uv pip install --python .venv/bin/python --find-links wheels sayfirst-cli==0.2.0 sayfirst-control-plane==0.2.0
 + sayfirst-boundary==0.2.0
 + sayfirst-cli==0.2.0
 + sayfirst-contract==0.2.0
 + sayfirst-control-plane==0.2.0
$ ls .venv/bin | grep '^sayfirst'
sayfirst
sayfirst-daemon
```

The first build writes fourteen artefacts (seven distributions, a wheel and a
source archive each); the second writes two. Only two distributions are
installed by name: the command you type, and the daemon that answers it. Two
more arrive as dependencies: the contract both share, and the boundary the
command carries for the programs it puts in front of the daemon. The other
distributions the first build produced (a stub, a conformance kit, a testing
kit, the daemon's operator surface) are not needed here.

`sayfirst --help` lists what the command answers today:

```console
$ .venv/bin/sayfirst --help
usage: sayfirst [-h]
                {ask,trace,explain,evidence,approvals,instrument,packs} ...
```

## 2. Write a policy and a configuration

The daemon reads one TOML policy file. This one names two capabilities: one it
allows on its own, one it holds for a person. Put your own account name in
`principals` — the reference is `user:` and the name `id -un` prints — because
the daemon establishes who is asking from the socket, and a rule names who it
is for.

```console
$ mkdir -p ~/.sayfirst/quickstart && chmod 700 ~/.sayfirst ~/.sayfirst/quickstart
```

`~/.sayfirst/quickstart/policy.toml`:

```toml
format = 1

[revision]
reason = "the first policy of this quickstart"

[[rule]]
id = "read-runs-on-its-own"
capability = "example.read"
principals = ["user:faime"]
outcome = "allow"
reason = "reading is reversible"

[[rule]]
id = "send-waits-for-a-person"
capability = "example.send"
principals = ["user:faime"]
outcome = "suspend"
reason = "a message that leaves the machine waits for a person"
review_deadline_seconds = 600
```

`~/.sayfirst/quickstart/daemon.toml` — per-user mode, no socket path: the
daemon chooses its default address, `$XDG_RUNTIME_DIR/sayfirst/daemon.sock`
where that variable is set and `~/.sayfirst/run/daemon.sock` otherwise, and
creates every level of the directory at `0700`:

```toml
[socket]
mode = "per_user"

[policy]
path = "/home/faime/.sayfirst/quickstart/policy.toml"

[evidence]
path = "/home/faime/.sayfirst/quickstart/evidence"
```

Both files are yours alone:

```console
$ chmod 600 ~/.sayfirst/quickstart/policy.toml ~/.sayfirst/quickstart/daemon.toml
```

## 3. Start the daemon

In a terminal of its own; it announces where it listens on its first line:

```console
$ .venv/bin/sayfirst-daemon serve --config ~/.sayfirst/quickstart/daemon.toml
serving per_user at /run/user/1000/sayfirst/daemon.sock (acl: checked)
```

Every command below takes that address as `--socket`; the walk kept it in a
variable, and so should you, with the address your daemon announced:

```console
$ S=/run/user/1000/sayfirst/daemon.sock
```

## 4. Ask

A capability the policy allows answers `allow` and exits `0`:

```console
$ .venv/bin/sayfirst ask --capability example.read --scope local --socket $S
verified: true (server_uid 1000, expected 1000)
outcome: allow
reason: policy_allows
capability: example.read in scope local
decision: 0acbb683-ea96-4f1c-9923-c492b4f0cb16 at 2026-09-16T23:15:32.289304Z
policy version: sha256:b7991fcab7f96d4af66efc769874ede67414efae3adadcfd3382b9f79754c724
```

The first line says the daemon proved who it is: the socket's owner is the
account you expected. A capability the policy holds for a person answers
`suspend`, names the wait, and exits `5`:

```console
$ .venv/bin/sayfirst ask --capability example.send --scope local --socket $S
verified: true (server_uid 1000, expected 1000)
outcome: suspend
reason: policy_requires_review
capability: example.send in scope local
decision: b6da8ac3-145f-4084-ac6c-74cf64ae7aff at 2026-09-16T23:15:32.366325Z
policy version: sha256:b7991fcab7f96d4af66efc769874ede67414efae3adadcfd3382b9f79754c724
approval: 43fda5a9-9a0e-4f6d-891f-5e24aa4d093c
```

Nothing was executed. Asking again while the wait is open returns the same
approval reference, not a second wait.

## 5. Answer as a person

Read the wait, then end it — once, with a reason if you want one recorded:

```console
$ A=43fda5a9-9a0e-4f6d-891f-5e24aa4d093c
$ .venv/bin/sayfirst approvals show --approval $A --scope local --socket $S
approval: 43fda5a9-9a0e-4f6d-891f-5e24aa4d093c
decision: b6da8ac3-145f-4084-ac6c-74cf64ae7aff
state: pending
requested_at: 2026-09-16T23:15:32.366325Z
deadline: 2026-09-16T23:25:32.366325Z
resolved_at: not stated
reason: not stated
$ .venv/bin/sayfirst approvals approve --approval $A --scope local --socket $S --reason "checked by hand"
approval: 43fda5a9-9a0e-4f6d-891f-5e24aa4d093c
decision: b6da8ac3-145f-4084-ac6c-74cf64ae7aff
state: approved
requested_at: 2026-09-16T23:15:32.366325Z
deadline: 2026-09-16T23:25:32.366325Z
resolved_at: 2026-09-16T23:15:43.269197Z
reason: checked by hand
```

The deadline is the policy's `review_deadline_seconds` after the ask. The
same question, asked again, is now allowed — with the reason that says why:

```console
$ .venv/bin/sayfirst ask --capability example.send --scope local --socket $S
verified: true (server_uid 1000, expected 1000)
outcome: allow
reason: approval_granted
capability: example.send in scope local
decision: bcfc5e6e-1c85-4637-9d4a-2373fd4d4995 at 2026-09-16T23:15:43.331201Z
policy version: sha256:b7991fcab7f96d4af66efc769874ede67414efae3adadcfd3382b9f79754c724
approval: 43fda5a9-9a0e-4f6d-891f-5e24aa4d093c
```

That allow is the one execution the person's act authorised. `approvals
reject` ends a wait the other way, and the next ask of that question is a
`deny` with reason `approval_rejected`.

## 6. Two answers that are not permission

A capability no rule names is denied, and the reason says so — the policy is
absent for it, not consulted and silent:

```console
$ .venv/bin/sayfirst ask --capability example.delete --scope local --socket $S
verified: true (server_uid 1000, expected 1000)
outcome: deny
reason: policy_absent
capability: example.delete in scope local
decision: 3a0a514a-3215-4284-a772-07fd6c8a10ec at 2026-09-16T23:15:56.548057Z
policy version: sha256:b7991fcab7f96d4af66efc769874ede67414efae3adadcfd3382b9f79754c724
$ echo $?
1
```

A daemon that is not there is reported as its own kind of answer, exit `4`,
never as a denial and never as permission:

```console
$ .venv/bin/sayfirst ask --capability example.read --scope local --socket /run/user/1000/sayfirst/absent.sock
verified: false (server_uid not stated, expected not stated)
could not ask: unreachable: [Errno 2] No such file or directory
retryable: true
$ echo $?
4
```

The exit codes, in one line: `0` allow, `1` deny, `5` suspend, `3` the request
was refused, `4` the control plane could not be asked.

## 7. Read back what happened

The evidence chain is paged from a sequence number; `--all` follows every
page. Each line is a sequence, a kind, the connection it belongs to and the
entry's hash:

```console
$ .venv/bin/sayfirst evidence history --scope local --socket $S --from 1 --all
1 composition daemon e81dcf376977f664fc207ed64e04b5212c6b5052d759a77d288ec0265de13610
2 grade a6f0ddb7-98ba-4508-aebe-b999b37854d3 39d7dbb7f55fcec0ad717c61d0efb85da3f1bf957a9457aa331fa81e729a1a5f
3 effect a6f0ddb7-98ba-4508-aebe-b999b37854d3 8d74bf759adf55eceb69e1ac95b3bd4b5d83201764bf8e3173dcb67300aee40e
…
next_from: none
```

Every read is itself recorded: `history`, `explain`, `trace` and `export`
each append an entry to the chain, so the counts on this page hold for this
page's exact sequence of commands, and one extra command of yours adds one
entry. Nothing is lost by that; it is the chain doing its job.

One decision, explained in the daemon's own words — the rule it applied and
the policy version it ran under — and traced into the chain that holds it:

```console
$ D=0acbb683-ea96-4f1c-9923-c492b4f0cb16
$ .venv/bin/sayfirst explain --scope local --socket $S --decision $D
decision_ref: 0acbb683-ea96-4f1c-9923-c492b4f0cb16
scope: local
capability: example.read
outcome: allow
reason: policy_allows
rule_id: read-runs-on-its-own
policy_version: sha256:b7991fcab7f96d4af66efc769874ede67414efae3adadcfd3382b9f79754c724
decided_at: 2026-09-16T23:15:32.289304Z
…
principal: {'kind': 'user', 'name': 'faime', 'uid': 1000}
principal_references: ['user:faime']
$ .venv/bin/sayfirst trace --scope local --socket $S --decision $D | tail -1
chain: sequence 3, entry_hash 8d74bf759adf55eceb69e1ac95b3bd4b5d83201764bf8e3173dcb67300aee40e, grade observability
```

## 8. Export, and verify offline

A bundle taken while the daemon's current epoch is open is checked as far as
it can be, and says so: the chain is intact and the manifest recomputes, but
coverage is `unknown`, and the command exits `7`, which means « could not
check », not « broken »:

```console
$ .venv/bin/sayfirst evidence export --scope local --socket $S --from 1 --out bundle.json
local_check: unverifiable
manifest: recomputes
chain: intact
coverage: unknown
issue: coverage_unknown
verification: intact
saved: bundle.json (12 entries)
```

Stop the daemon cleanly (`Ctrl-C`, or `kill -TERM` on its process); it closes
the epoch and removes its socket. Start it again and export the range that
ends at the closing marker — here sequence 13, the entry after the last
effect — and coverage is `complete`:

```console
$ .venv/bin/sayfirst evidence export --scope local --socket $S --from 1 --to 13 --out closed.json
local_check: unverifiable
manifest: recomputes
chain: intact
coverage: complete
verification: intact
saved: closed.json (13 entries)
```

The local check still answers `unverifiable`, and `--json` says exactly why:
three of the four decisions re-derive from the policy alone and are
`confirmed` — the allow, the suspension and the denial — while the fourth,
the allow a person granted, has the cause `reason_outside_recipe`. A
decision a person made cannot be re-derived from a policy file, and the
verifier says so rather than counting it. That is the honest verdict, not a
fault, and it is what a third party sees too: `sayfirst evidence exports
DIRECTORY` re-verifies every bundle saved in a directory with the contract
distribution alone, no daemon needed.

```console
$ .venv/bin/sayfirst evidence exports .
bundle.json local 1..12 served:intact local:unverifiable
closed.json local 1..13 served:intact local:unverifiable
```

An export refuses to overwrite a bundle that exists (`refusing to overwrite`,
exit `64`); name a new file.

## 9. Stop, and where this goes next

`kill -TERM` the daemon, or `Ctrl-C` in its terminal. It leaves the socket
directory empty and the evidence under the path the configuration named.

- `sayfirst packs list` prints the three convenience packs this distribution
  ships — `database`, `http-client`, `subprocess` — and `sayfirst instrument
  run` puts the boundary in front of a program whose effects are library
  calls; the README describes both.
- A program can compose the boundary by hand from the `sayfirst-boundary`
  distribution instead. The governed-agent demonstration does exactly that,
  against this same daemon.
- The control plane's `docs/deployment.md` describes system mode, where one
  daemon serves several accounts admitted by a group.
