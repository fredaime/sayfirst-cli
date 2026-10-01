<!-- SPDX-License-Identifier: Apache-2.0 -->
# Quickstart

Three commands take a machine from nothing to a real control plane governing a
Python program you already have:

```console
$ uv tool install sayfirst-cli --with-executables-from sayfirst-control-plane --with-executables-from sayfirstd
$ sayfirst-daemon up --quickstart
$ sayfirst instrument run --pack subprocess --scope local -- python3 my_agent.py
```

Everything on this page was run, in this order, before it was written down: the
commands are pasted from a run, and so are their answers. The walk recorded for
this release installed 0.3.3 with the first command from wheels built from the
two release trees, given `--no-index` (it ran before 0.3.3 reached the index;
« From checkouts instead » below is that install), on a PATH with `python3` and
no `python`, in a shell with neither repository on any path, under a home
directory made for it. It answered in the same shapes as the walk whose answers
are printed here, which is an earlier release's: only the five versions of
section 1 were moved. Paths are written the way they read under an ordinary
account (`~`, and `/run/user/1000` for the runtime directory). Your
identifiers, timestamps, sizes and hashes will differ; the shapes will not.

## What you need

- Linux or macOS. The control plane listens on a local socket and reads who
  is calling from the kernel; there is no port and nothing that takes a token.
- Python 3.12, 3.13 or 3.14 as `python3` on your PATH (Linux distributions
  and macOS name it that; inside an activated virtual environment `python`
  works too), and [`uv`](https://docs.astral.sh/uv/). The walk used
  uv 0.12.
- A home directory that only you can write. The daemon refuses to start if
  the socket's directory, or any directory on the way to it, can be written
  by a group or by others and is not sticky (`socket_directory_unprotected`),
  and likewise for the policy's directory and those above it
  (`policy_unavailable_at_start … exposed: group_write`); either way it says
  so instead of starting.

## 1. Install

```console
$ uv tool install sayfirst-cli --with-executables-from sayfirst-control-plane --with-executables-from sayfirstd
Resolved 5 packages in 3ms
Prepared 5 packages in 6ms
Installed 5 packages in 1ms
 + sayfirst-boundary==0.3.3
 + sayfirst-cli==0.3.3
 + sayfirst-contract==0.3.3
 + sayfirst-control-plane==0.3.3
 + sayfirstd==0.3.3
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

**From checkouts instead.** A contributor installs the same thing from the two
repositories' trees,
<https://github.com/fredaime/sayfirst-control-plane> and
<https://github.com/fredaime/sayfirst-cli>: build the wheels, then install them
with nothing fetched.

```console
$ (cd /path/to/sayfirst-control-plane && uv build --all-packages --wheel --out-dir ~/wheels)
$ (cd /path/to/sayfirst-cli && uv build --wheel --out-dir ~/wheels)
$ uv tool install --no-index --find-links ~/wheels sayfirst-cli --with-executables-from sayfirst-control-plane --with-executables-from sayfirstd
```

`--no-index` keeps the install to the wheels you built: the index carries the
same version numbers, and an installer allowed to look there could take the
published files instead of your trees.

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
pid: 741184
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
total 16
drwx------ 3 you you  160 Sep 29 01:06 .
drwx------ 3 you you   60 Sep 29 01:06 ..
-rw------- 1 you you    0 Sep 29 01:06 daemon.lock
-rw------- 1 you you   76 Sep 29 01:06 daemon.log
-rw------- 1 you you  260 Sep 29 01:06 daemon.run.json
-rw------- 1 you you  598 Sep 29 01:06 daemon.toml
drwx------ 5 you you  120 Sep 29 01:06 evidence
-rw------- 1 you you 3008 Sep 29 01:06 policy.toml
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
$ sayfirst instrument run --pack subprocess --scope local -- python3 my_agent.py
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
- **`python3` means your `python3`.** The program is handed to the interpreter
  you named, found the way your shell finds it, with the boundary installed in
  that process — so a program living in a project's environment keeps its own
  dependencies. Here `~/project` has an environment of its own
  (`uv venv`, then `uv pip install humanize`) holding a package the `sayfirst`
  tool does not, and `real_agent.py` uses it:

```python
import sys

import humanize

print("hello from the project's own interpreter")
print("running under", sys.prefix)
print("imported:", humanize.naturalsize(1_000_000))
```

  In `~/project`, with its environment activated, `python3` is that
  environment's:

```console
$ . .venv/bin/activate
$ sayfirst instrument run --pack subprocess --scope local -- python3 real_agent.py
hello from the project's own interpreter
running under ~/project/.venv
imported: 1.0 MB
```

  Without the activation the same command finds the system `python3`, and the
  program stops at its import (`ModuleNotFoundError: No module named 'humanize'`).

  An agent started as a console script rather than as `python3 …` is handed
  over the same way: `-- ./myagent` reads the executable's shebang
  (`#!…/.venv/bin/python`) and runs it under that interpreter. Named without an
  interpreter (`-- my_agent.py`, or `-- -m package`), a program runs inside the
  interpreter that carries `sayfirst` itself, which as a `uv` tool has none of
  your project's packages. A runner in that place — `-- uv run app.py` — is
  refused, because it would pick an interpreter the boundary is not in; name the
  interpreter instead. The named interpreter has to be Python 3.12 or later. An
  option after the interpreter's name is refused (`-- python3 -u real_agent.py`
  exits `64`: « found no file to run at '-u' »); an option the interpreter also
  reads from the environment reaches it that way —
  `PYTHONUNBUFFERED=1 sayfirst instrument run …` runs the program unbuffered.
  A `python` the shell cannot find is refused (`64`), and the refusal says the
  same PATH has a `python3`.

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
1 composition daemon b7e07cc5149332bda660b2bfd874409cc3c43c3fcc545bcdfe434eeca08d7992
2 grade 5ca3ce19-2d93-44de-839a-a25148efacc4 8e500b2d2f634f07ed10e70b769b0d170821bd07d9121c5fcdabbb914fdf4d66
3 grade bc12e161-76be-4939-80d2-711c7ba145d8 614359e106f698383cc7da518ebd5714be580e70acf0ae9e3b9141b40a83ecb4
4 effect bc12e161-76be-4939-80d2-711c7ba145d8 effeb84e48ae71368bd796198d1a49c256c4f7c381f72d11d3e7dc5567355d5e
5 grade 8abbfb3c-a3b1-4ca1-8f74-fc732ffa7caa c5a7e9be2d2af3fd0dbb3d691caa7a4019a06dcf1dea34417acece0cb91753ea
6 grade 8af05baa-2b94-47f9-acdc-3d9dbd51850e 55e018d5ba3cfd56f7e812351b3a6762bb3006e0209eaf30a27cb722c008167a
next_from: none
```

Each `effect` line is one decision about one governed call.

## 4. Change the policy

Open `~/.sayfirst/quickstart/policy.toml`, find the rule for `process.spawn`,
and change one word — `outcome = "allow"` to `outcome = "deny"`. Save. Nothing
is restarted; the daemon reads the file when it decides.

```console
$ sayfirst instrument run --pack subprocess --scope local -- python3 my_agent.py
Traceback (most recent call last):
  …
sayfirst_boundary.errors.Denied: denied: process.spawn (policy_denies, 47339de8-e6c3-4b2f-8c91-7eaa6a53aa26)
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
$ sayfirst instrument run --pack subprocess --scope local -- python3 my_agent.py
Traceback (most recent call last):
  …
sayfirst_boundary.errors.Suspended: suspended: process.spawn awaits approval 93684c01-f9e8-4f27-9ad8-6c2be85306c5
$ echo $?
5
```

Nothing ran, and a person is being waited for. Read the wait, then end it:

```console
$ sayfirst approvals show --approval 93684c01-f9e8-4f27-9ad8-6c2be85306c5 --scope local
approval: 93684c01-f9e8-4f27-9ad8-6c2be85306c5
decision: ace43a8a-88ad-4907-8e91-4e978af85604
state: pending
requested_at: 2026-09-28T23:06:51.035245Z
deadline: 2026-09-28T23:11:51.035245Z
resolved_at: not stated
reason: not stated
$ sayfirst approvals approve --approval 93684c01-f9e8-4f27-9ad8-6c2be85306c5 --scope local --reason "checked by hand"
approval: 93684c01-f9e8-4f27-9ad8-6c2be85306c5
decision: ace43a8a-88ad-4907-8e91-4e978af85604
state: approved
requested_at: 2026-09-28T23:06:51.035245Z
deadline: 2026-09-28T23:11:51.035245Z
resolved_at: 2026-09-28T23:06:51.216909Z
reason: checked by hand
person: user:you
$ sayfirst instrument run --pack subprocess --scope local -- python3 my_agent.py
hello
```

That run is the one execution the person's act authorised: run it once more and
it waits again, under a new approval. Running it *while* the wait is open
returns the same approval rather than opening a second. `approvals reject` ends
a wait the other way: every run of the same program is then denied with
`approval_rejected` until that wait's deadline — five minutes here, since the
rule you edited names no `review_deadline_seconds` — and a restart of the daemon
forgets it.

## 5. Prove it

Put the rule back to `"allow"`, and ask for proof rather than a run:

```console
$ sayfirst instrument verify --pack subprocess --scope local -- python3 my_agent.py
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
SayFirst Control Plane stopped (pid 741184)
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
```

It exits `4`, like every read that could not ask.

```console
$ sayfirst ask --capability process.spawn
socket: /run/user/1000/sayfirst/daemon.sock (the per-user default; no --socket was given)
verified: false (server_uid not stated, expected not stated)
could not ask: unreachable: [Errno 2] No such file or directory
retryable: true
$ echo $?
4
$ sayfirst instrument run --pack subprocess --scope local -- python3 my_agent.py
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

Section 6 left the control plane stopped; start it again:

```console
$ sayfirst-daemon up --quickstart
SayFirst Control Plane ready
…
```

The same three outcomes without a program. `--scope` defaults to `local` for
`ask`, and every other read names it:

```console
$ sayfirst ask --capability process.spawn
verified: true (server_uid 1000, expected 1000)
outcome: allow
reason: policy_allows
capability: process.spawn in scope local
decision: 86c6debb-715a-4f28-9aa8-75026a395f48 at 2026-09-28T23:06:52.489393Z
policy version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
$ sayfirst ask --capability net.egress
verified: true (server_uid 1000, expected 1000)
outcome: suspend
reason: policy_requires_review
capability: net.egress in scope local
decision: 30fac8bc-d1a1-4058-a7c4-1ff62e4db58d at 2026-09-28T23:06:52.574755Z
policy version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
approval: 335902ec-3ece-4b06-8856-9d45ef78e2e2
$ sayfirst ask --capability database.open
verified: true (server_uid 1000, expected 1000)
outcome: deny
reason: policy_absent
capability: database.open in scope local
decision: e2791157-0385-4a79-86d0-abfb97cd83b4 at 2026-09-28T23:06:52.655469Z
policy version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
```

The first line of each says the daemon proved who it is: the socket's owner is
the account you expected. The three exit `0`, `5` and `1`. The denial's reason
is `policy_absent`: no rule names the capability, which is not the same as a
rule saying no.

One decision, explained in the daemon's own words and traced into the chain:

```console
$ sayfirst explain --scope local --decision 86c6debb-715a-4f28-9aa8-75026a395f48
decision_ref: 86c6debb-715a-4f28-9aa8-75026a395f48
scope: local
capability: process.spawn
outcome: allow
reason: policy_allows
rule_id: local-processes-run
policy_version: sha256:efc1746cea9b50cb31aa5c9f08de996cbefabc34a09d4250d8b68f67c709a5dc
decided_at: 2026-09-28T23:06:52.489393Z
…
$ sayfirst trace --scope local --decision 86c6debb-715a-4f28-9aa8-75026a395f48 | tail -1
chain: sequence 23, entry_hash ee313608e9c4f09b747c7ec9ac5d817e0945bbeb7b9f267f76f1d2c2c4e935d5, grade observability
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
saved: bundle.json (29 entries)
```

### A closed epoch, verified

`down` closes the daemon's evidence epoch and `up` opens the next, and only a range
inside a closed epoch can be checked whole. The history shows where the epoch closed —
the `recovery` entry just before the next `composition`:

```console
$ sayfirst evidence history --scope local --from 1 --all | grep -E 'recovery|composition'
1 composition daemon b7e07cc5149332bda660b2bfd874409cc3c43c3fcc545bcdfe434eeca08d7992
19 recovery daemon f36c43ff25d8a0c15b64dd55a089127fcab352ffa056420c536314ad63c76a3b
20 composition daemon 17c41de74accb1d7b03bf8864229f370c446623d9f528eae1f5387c22cb6463e
```

Export up to that entry with `--to`:

```console
$ sayfirst evidence export --scope local --from 1 --to 19 --out closed.json
local_check: unverifiable
manifest: recomputes
chain: intact
coverage: complete
verification: intact
saved: closed.json (19 entries)
```

Coverage is `complete` — nothing in that range is missing — and the check still says
`unverifiable`, exit `7`, because section 4 put a person in that range: an approval,
and every decision that follows from one — the run it authorised, and any
`approval_rejected` denial — re-derives as `unverifiable` with the cause
`reason_outside_recipe`. A policy file cannot re-derive a human act, and the
verifier says so rather than counting it (`--json` shows each decision's
cause). A range with no person's act in it verifies — here the same epoch up
to the suspension's own entry, before anyone answered it (`sayfirst trace` on
the suspended decision names its sequence):

```console
$ sayfirst evidence export --scope local --from 1 --to 10 --out quiet.json
local_check: confirmed
manifest: recomputes
chain: intact
coverage: complete
verification: intact
saved: quiet.json (10 entries)
```

The epoch `up` opened in this section is still open, so a range inside it is
`coverage: unknown` until the next `down` closes it.

`sayfirst evidence exports DIRECTORY` re-verifies every saved bundle with the contract
distribution alone, no daemon needed, and exits with the worst result among them.
An export never writes over a file: naming one that exists is refused (`64`).

## 8. A control plane of your own

The quickstart is a convenience over one command, and everything it does can be
done by hand — which is what a deployment does, under its own supervisor:

```console
$ sayfirst-daemon serve --config /path/to/daemon.toml
serving per_user at /run/user/1000/sayfirst/daemon.sock (acl: checked)
```

`daemon.toml` names the mode, the policy file and the evidence directory, all
absolute; `~/.sayfirst/quickstart/daemon.toml` is a working example. Stop the
quickstart daemon first (`sayfirst-daemon down`), or give the copy an
`[evidence] path` and a `[socket] path` of its own: two daemons never share an
evidence directory (`decision_store_unusable`) nor an address (`socket_in_use`),
and the second refuses to start. Given a `[socket] path`, the daemon serves
there instead, and every client command takes the same path as `--socket`:

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
