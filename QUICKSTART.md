<!-- SPDX-License-Identifier: Apache-2.0 -->
# Quickstart

Three commands take a machine from nothing to a real control plane governing a
Python program you already have:

```console
$ uv tool install sayfirst-cli --with-executables-from sayfirst-control-plane --with-executables-from sayfirstd
$ sayfirst-daemon up --quickstart
$ sayfirst instrument run --pack subprocess --scope local -- python my_agent.py
```

Everything on this page was run, in this order, before it was written down: the
commands are pasted from that run, and so are their answers. The run used
distributions built from this tree and installed by the first command, in a
shell with neither repository on any path, under a home directory made for it;
its paths are written here the way they read under an ordinary account (`~`, and
`/run/user/1000` for the runtime directory). Your identifiers, timestamps and
hashes will differ; the shapes will not.

## What you need

- Linux or macOS. The control plane listens on a local socket and reads who
  is calling from the kernel; there is no port and nothing that takes a token.
- Python 3.12, 3.13 or 3.14, and [`uv`](https://docs.astral.sh/uv/). The walk
  used uv 0.12.
- A home directory that only you can write. The daemon refuses to put its
  socket below a directory a group can write and that is not sticky
  (`socket_directory_unprotected`), and it says so instead of starting.

## 1. Install

```console
$ uv tool install sayfirst-cli --with-executables-from sayfirst-control-plane --with-executables-from sayfirstd
 + sayfirst-boundary==0.3.0
 + sayfirst-cli==0.3.0
 + sayfirst-contract==0.3.0
 + sayfirst-control-plane==0.3.0
 + sayfirstd==0.3.0
Installed 1 executable from `sayfirst-control-plane`: sayfirst-daemon
Installed 1 executable from `sayfirstd`: sayfirstd
Installed 1 executable: sayfirst
```

One environment, three commands: `sayfirst` is the client you type, the daemon
is `sayfirst-daemon`, and `sayfirstd` is the daemon's operator surface
(`status`, `whoami`). `uv tool install` takes one package, which is why the
other two ride on `--with-executables-from`; three separate `uv tool install`
lines, or `pip install sayfirst-cli sayfirst-control-plane sayfirstd` in an
environment of your own, install the same thing.

**What the index holds is not yet what this page installs.** `sayfirst-cli`
0.2.0 is on the index and predates everything below: it has no default socket,
reads `--pack` as a path only, and refuses `python` as the first word of a
target. `sayfirst-control-plane` and `sayfirstd` are not on the index at all as
this is written. Until a release carries this page, install from checkouts of
the two repositories,
<https://github.com/fredaime/sayfirst-control-plane> and
<https://github.com/fredaime/sayfirst-cli> — which is what the walk did:

```console
$ (cd /path/to/sayfirst-control-plane && uv build --all-packages --wheel --out-dir ~/wheels)
$ (cd /path/to/sayfirst-cli && uv build --wheel --out-dir ~/wheels)
$ uv tool install --no-index --find-links ~/wheels sayfirst-cli --with-executables-from sayfirst-control-plane --with-executables-from sayfirstd
```

`--no-index` keeps the install to the wheels you built: nothing is fetched, so
what runs is exactly those two trees — and two of the five distributions are
not on the index to be fetched anyway.

## 2. Start a control plane

```console
$ sayfirst-daemon up --quickstart
SayFirst Control Plane ready
mode: per_user
socket: /run/user/1000/sayfirst/daemon.sock
policy: ~/.sayfirst/quickstart/policy.toml
evidence: ~/.sayfirst/quickstart/evidence
integrity grade: observability (the caller can write the store; the chain detects accidental corruption only)
grade re-evaluation interval: 30 seconds
privacy provider: none (captured content is recorded as given)
evidence emission: delivering
log: ~/.sayfirst/quickstart/daemon.log
pid: 1622067
wrote: ~/.sayfirst/quickstart/policy.toml
wrote: ~/.sayfirst/quickstart/daemon.toml
stop: sayfirst-daemon down
```

That is the real daemon — the one `sayfirst-daemon serve --config` starts —
running in the background, in per-user mode, on two files it wrote because they
were not there. « Ready » is said only after the daemon has **answered** a
status request over its socket, and the four lines from `integrity grade:` down
are that answer, in the daemon's own words. The grade is `observability`
because in per-user mode you can write the store you are asking about; the
quickstart does not get to say anything better than the daemon does.

Everything lives in one private directory (`0700`, files `0600`):

```console
$ ls -la ~/.sayfirst/quickstart
drwx------ 3 you you  160 .
-rw------- 1 you you    0 daemon.lock
-rw------- 1 you you   75 daemon.log
-rw------- 1 you you  259 daemon.run.json
-rw------- 1 you you  596 daemon.toml
drwx------ 5 you you  120 evidence
-rw------- 1 you you 3008 policy.toml
```

`daemon.run.json` is what `up` knows about the daemon it started: its pid, the
instant the kernel says that process began (tied to this boot), and the socket,
policy and evidence it was started on. `daemon.lock` is taken by `up` and `down`
while they read that record, start or stop the daemon, and write the record
back, so two of them never race; the daemon itself does not hold it.

**`policy.toml` is yours.** Open it: it is commented TOML that says what a rule
is and what the three outcomes mean, and it starts with three behaviours so
that each can be seen without an edit — starting a process (`process.spawn`)
is allowed, opening a URL (`net.egress`, what `--pack http-client` asks about)
waits for a person, and opening a database (`database.open`) is named by no
rule and is therefore denied. It names your account, because a rule is for the
principals it names; the daemon learns who is asking from the socket, never
from the file.

**Running the command again never writes over it.** A second `up --quickstart`
finds the daemon it started and says `SayFirst Control Plane already running`;
after a `down` it starts again on the files as you left them. A file is only
ever written when it is missing — delete `policy.toml` to get the starter back.
A policy the daemon cannot read is the daemon's own refusal
(`policy_unavailable_at_start`, exit `78`), never a reason to replace your file.

## 3. Govern a program

`my_agent.py`, in a directory of its own:

```python
import subprocess

subprocess.run(["echo", "hello"], check=True)
```

```console
$ sayfirst instrument run --pack subprocess --scope local -- python my_agent.py
hello
```

The program ran with the boundary in front of `subprocess`: before the process
was started the control plane was asked, it answered `allow`, and it recorded
that. Three things in that line are worth a sentence each.

- **`--pack subprocess` is an instrumentation pack, not a policy.** A pack says
  *which calls are asked about* — here, starting a process, under the
  capability `process.spawn`. What the answer is belongs to the policy, in the
  daemon. A bare word names a pack this distribution ships (`sayfirst packs
  list`: `database`, `http-client`, `subprocess`); a pack of your own is a
  directory, spelled with a separator: `--pack ./my-pack`.
- **No `--socket`.** A per-user daemon given no address serves at
  `$XDG_RUNTIME_DIR/sayfirst/daemon.sock` (or `~/.sayfirst/run/daemon.sock`
  where there is no runtime directory), and a client given none looks at that
  one name. Nothing is searched for, and whoever answers is still verified to be
  your own account's process before a byte is sent. `--socket PATH` overrides
  it, and system mode always names it.
- **`python` means your `python`.** The program is handed to the interpreter
  you named, found the way your shell finds it, with the boundary installed in
  that process — so a program living in a project's environment keeps its own
  dependencies:

```console
$ sayfirst instrument run --pack subprocess --scope local -- python real_agent.py
hello from the project's own interpreter
running under ~/project/.venv
imported: a dependency only the project has
```

  An agent started as a console script rather than as `python …` is handed
  over the same way: `-- ./myagent` reads the executable's shebang
  (`#!…/.venv/bin/python`) and runs it under that interpreter. Named without an
  interpreter (`-- my_agent.py`, or `-- -m package`), a program runs inside the
  interpreter that carries `sayfirst` itself, which as a `uv` tool has none of
  your project's packages. A runner in that place — `-- uv run app.py` — is
  refused, because it would pick an interpreter the boundary is not in; name the
  interpreter instead. The named interpreter has to be Python 3.12 or later, and
  interpreter options (`python -u …`) are not carried.

What the control plane recorded, read back from it:

```console
$ sayfirstd status
verified: true (server_uid 1000, expected 1000)
contract generation: 1 (supported: 1)
integrity grade: observability (the caller can write the store; the chain detects accidental corruption only)
grade re-evaluation interval: 30 seconds
privacy provider: none (captured content is recorded as given)
evidence emission: delivering
$ sayfirst evidence history --scope local --from 1 --all
1 composition daemon 2b12918b5588b2e3b50efa80fb7035ead2d2579537d991118f92b05bc0c0cfb3
2 grade b5b86aba-5d1b-4b47-8059-38783a488547 7f6c25dfac3eac4ee6174aff24630eaf8f8804d96436a0daf160644e8195806f
3 grade 7750b836-8ee2-4d2b-8de5-2c9d96b16e75 ca6a3b37ba461f63b70ae8b6d16641c4b1d446be7fbb428a9d50db38c2c55d1e
4 grade 0db649e3-d5c9-4145-b05a-feb2ed6c1344 23ca566a49a282624fc21c1a65f467c2d437350682d0ad6dfe131e429f76fdc7
5 effect 0db649e3-d5c9-4145-b05a-feb2ed6c1344 13776e23385f7a6fa0aff7a01af3a3e090ea3be27a7e9aeab83f93cb09dee791
…
next_from: none
```

Each `effect` line is one decision about one governed call.

## 4. Change the policy

Open `~/.sayfirst/quickstart/policy.toml`, find the rule for `process.spawn`,
and change one word — `outcome = "allow"` to `outcome = "deny"`. Save. Nothing
is restarted; the daemon reads the file when it decides.

```console
$ sayfirst instrument run --pack subprocess --scope local -- python my_agent.py
Traceback (most recent call last):
  …
sayfirst_boundary.errors.Denied: denied: process.spawn (policy_denies, 48293af4-5ab0-4c92-b16b-f0ca974a490b)
$ echo $?
1
```

No `hello`: the process was never started. The refusal is an exception raised
inside your program, at the call — yours to catch. A program that catches it
ends however it chooses; one that catches nothing ends with its traceback, and
`instrument run` then ends with that outcome's own status — `1` for a denial —
rather than the interpreter's `1` for any exception at all, which would read a
suspension or an unreachable control plane as a denial too.

Now `outcome = "suspend"`:

```console
$ sayfirst instrument run --pack subprocess --scope local -- python my_agent.py
Traceback (most recent call last):
  …
sayfirst_boundary.errors.Suspended: suspended: process.spawn awaits approval 55fc6d74-275b-4250-9a7f-58871bfc5bf1
$ echo $?
5
```

Nothing ran, and a person is being waited for. Read the wait, then end it:

```console
$ sayfirst approvals show --approval 55fc6d74-275b-4250-9a7f-58871bfc5bf1 --scope local
approval: 55fc6d74-275b-4250-9a7f-58871bfc5bf1
decision: 45faca76-852a-4991-a5fb-bc2190e42325
state: pending
requested_at: 2026-09-23T02:05:45.453931Z
deadline: 2026-09-23T02:10:45.453931Z
resolved_at: not stated
reason: not stated
$ sayfirst approvals approve --approval 55fc6d74-275b-4250-9a7f-58871bfc5bf1 --scope local --reason "checked by hand"
approval: 55fc6d74-275b-4250-9a7f-58871bfc5bf1
decision: 45faca76-852a-4991-a5fb-bc2190e42325
state: approved
requested_at: 2026-09-23T02:05:45.453931Z
deadline: 2026-09-23T02:10:45.453931Z
resolved_at: 2026-09-23T02:05:45.642267Z
reason: checked by hand
person: user:you
$ sayfirst instrument run --pack subprocess --scope local -- python my_agent.py
hello
```

That run is the one execution the person's act authorised: run it once more and
it waits again, under a new approval. Running it *while* the wait is open
returns the same approval rather than opening a second. `approvals reject` ends
a wait the other way, and the next run is denied with `approval_rejected`.

## 5. Prove it

Put the rule back to `"allow"`, and ask for proof rather than a run:

```console
$ sayfirst instrument verify --pack subprocess --scope local -- python my_agent.py
hello
governed subprocess subprocess.Popen process.spawn events=1
inspected: subprocess
target exit: 0
$ echo $?
0
```

`verify` runs the program under the interpreter's own audit hook and checks each
effect of a kind the pack names against the chain the daemon kept. `governed`
says exactly one thing: every such effect this run made was preceded by a
recorded `allow`, for your account, after the run began. It is not a claim
about paths the run did not take — a point no effect reached is `not-exercised`
and exits `7`, never `0` — nor about calls the pack does not interpose;
[`docs/PACKS.md`](docs/PACKS.md) states what the proof matches and what it does
not. The program's own output arrives on the error stream, so the report is
alone on stdout.

## 6. Stop, and what a stopped control plane means

```console
$ sayfirst-daemon down
SayFirst Control Plane stopped (pid 1622067)
policy and evidence are kept under ~/.sayfirst/quickstart
```

`down` stops the daemon `up` started and no other: it signals the recorded
process only when that process still began at the recorded instant, as the
kernel reports it for this boot. A record whose process is gone is removed and
nothing is signalled; a living process whose start this command cannot read is
left running, with its record, and `down` says so and exits `1`; a daemon you
started yourself with `serve` is left running, and `down` says so. The daemon
closes its evidence epoch on the way out, and removes its socket.

With no control plane, nothing is permitted and nothing is called a denial:

```console
$ sayfirstd status
socket: /run/user/1000/sayfirst/daemon.sock (the per-user default; no --socket was given)
verified: false (server_uid None, expected None)
unreachable: [Errno 2] No such file or directory
$ sayfirst ask --capability process.spawn
socket: /run/user/1000/sayfirst/daemon.sock (the per-user default; no --socket was given)
verified: false (server_uid not stated, expected not stated)
could not ask: unreachable: [Errno 2] No such file or directory
retryable: true
$ echo $?
4
$ sayfirst instrument run --pack subprocess --scope local -- python my_agent.py
socket: /run/user/1000/sayfirst/daemon.sock (the per-user default; no --socket was given)
nothing is there now, so an effect these packs name will fail closed; `sayfirst-daemon up --quickstart` starts a control plane at that address
Traceback (most recent call last):
  …
sayfirst_boundary.errors.CouldNotAsk: could not ask: [Errno 2] No such file or directory
$ echo $?
4
```

The effect did not happen. A governed program with nobody to ask fails closed,
ends « could not ask », and the address nobody typed is named so that you know
where it looked.

The exit codes of `sayfirst ask`, in one line: `0` allow, `1` deny, `5`
suspend, `3` the request was refused, `4` the control plane could not be asked —
and `instrument run` ends with the same numbers when a program lets the outcome
escape.

## 7. Asking by hand, and reading back

The same three outcomes without a program. `--scope` defaults to `local` for
`ask`, and every other read names it:

```console
$ sayfirst ask --capability process.spawn
verified: true (server_uid 1000, expected 1000)
outcome: allow
reason: policy_allows
capability: process.spawn in scope local
decision: 52ff1ab5-8813-4230-9ca4-2f272612c64d at 2026-09-23T02:05:47.180188Z
policy version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
$ sayfirst ask --capability net.egress
verified: true (server_uid 1000, expected 1000)
outcome: suspend
reason: policy_requires_review
capability: net.egress in scope local
decision: 5cb90b68-bb1a-4674-ae2d-97a1bd9c5797 at 2026-09-23T02:05:47.255248Z
policy version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
approval: d058eee2-4ecc-488c-837d-037e206c1247
$ sayfirst ask --capability database.open
verified: true (server_uid 1000, expected 1000)
outcome: deny
reason: policy_absent
capability: database.open in scope local
decision: c6284ad7-f77b-4367-a50d-977489e2f6f7 at 2026-09-23T02:05:47.335332Z
policy version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
```

The first line of each says the daemon proved who it is: the socket's owner is
the account you expected. The three exit `0`, `5` and `1`. The denial's reason
is `policy_absent`: no rule names the capability, which is not the same as a
rule saying no.

One decision, explained in the daemon's own words and traced into the chain:

```console
$ sayfirst explain --scope local --decision 474856fc-e891-46ac-844c-efa30cc9322f
decision_ref: 474856fc-e891-46ac-844c-efa30cc9322f
scope: local
capability: process.spawn
outcome: allow
reason: policy_allows
rule_id: local-processes-run
policy_version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
decided_at: 2026-09-23T02:05:47.410354Z
…
$ sayfirst trace --scope local --decision 474856fc-e891-46ac-844c-efa30cc9322f | tail -1
chain: sequence 34, entry_hash 0d00934b16b3dc0004d7e13c884b83aec61a79dfb6d43278dab3530d1f8250d7, grade observability
```

Every read is itself recorded: `history`, `explain`, `trace` and `export` each
append an entry to the chain, so one extra command of yours adds one entry.

A bundle exported while the daemon's current epoch is open is checked as far as
it can be and says so — the chain is intact and the manifest recomputes, but
coverage is `unknown`, and the command exits `7`, « could not check », not
« broken »:

```console
$ sayfirst evidence export --scope local --from 1 --out bundle.json
local_check: unverifiable
manifest: recomputes
chain: intact
coverage: unknown
issue: coverage_unknown
verification: intact
saved: bundle.json (36 entries)
```

After a `down` and an `up`, the range that ends at the closed epoch's last entry
exports with coverage `complete`; `sayfirst evidence exports DIRECTORY`
re-verifies every saved bundle with the contract distribution alone, no daemon
needed. A decision a person granted re-derives as `unverifiable` with the cause
`reason_outside_recipe`, by design: an approval cannot be re-derived from a
policy file, and the verifier says so rather than counting it.

## 8. A control plane of your own

The quickstart is a convenience over one command, and everything it does can be
done by hand — which is what a deployment does, under its own supervisor:

```console
$ sayfirst-daemon serve --config /path/to/daemon.toml
serving per_user at /run/user/1000/sayfirst/daemon.sock (acl: checked)
```

`daemon.toml` names the mode, the policy file and the evidence directory, all
absolute; `~/.sayfirst/quickstart/daemon.toml` is a working example. Given a
`[socket] path`, the daemon serves there instead, and every client command
takes the same path as `--socket`:

```console
$ sayfirst ask --capability process.spawn --socket /srv/sayfirst/daemon.sock
$ sayfirst instrument run --pack /srv/packs/own-pack --scope local --socket /srv/sayfirst/daemon.sock -- app.py
```

System mode — one daemon, several accounts admitted by a group — is described
in the control plane's `docs/deployment.md`. A system profile always names both
the socket and the account the daemon runs as (`--mode system --socket PATH
--daemon-user NAME`); neither is ever defaulted, because a default there would
let a profile written for one host verify the wrong thing on another.

A program can also compose the boundary by hand from the `sayfirst-boundary`
distribution instead of being launched by `instrument run`; the governed-agent
demonstration does exactly that, against this same daemon.
