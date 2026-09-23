<!-- SPDX-License-Identifier: Apache-2.0 -->
# Changelog

Every release of this client carries a section here, named for the version the project file
declares; a release with no section fails the gate.

## Unreleased

## 0.3.0

- **`--socket` is optional for a per-user profile**, on every verb that opens a connection. Given
  none, the client looks at the per-user default address — the contract's own rule, the one a
  per-user daemon given no address binds by — and at nothing else: nothing is searched for, and
  whoever answers is still verified to be the expected account's process before a byte is sent. A
  `--socket` somebody typed is the address. A system profile is never given one and still names
  it (`64` otherwise). **What changes for a caller:** an invocation with no `--socket` used to end
  as a usage error (`2`); it now asks, and with nobody at the default address it answers « could
  not ask » (`4`), naming the address it looked at. `evidence audit` with neither `--file` nor
  `--socket` is an online audit at that address rather than a usage error. Needs the contract
  distribution that publishes the rule, which is the one after 0.2.0.
- **`--pack` takes the name of a pack this distribution ships** (`--pack subprocess`), as well as
  a directory. The spelling alone decides: a designation with a path separator in it, or `.` or
  `..`, is a directory; a bare word is a shipped pack's name and is never read as a directory of
  the working directory. **What changes for a caller:** a pack directory designated by a bare
  relative word (`--pack own-pack`) is now refused (`64`) with the spelling that names it
  (`--pack ./own-pack`). Absolute paths and paths with a separator are read exactly as before.
  `packs check` takes the same two spellings. `docs/PACKS.md` says why this is a designation and
  not a registry.
- **A target whose first word is `python`, `python3` or `python3.N` is run by that interpreter.**
  The whole command is handed to it, the boundary is installed in that process, and the client,
  the boundary and the contract are lent to it by name — three packages and their metadata, and
  nothing else of this environment. A program in a project's own environment therefore keeps its
  dependencies when this client is installed as a tool. The interpreter has to be Python 3.12 or
  later, and interpreter options are not carried. Before this, such a target was refused (`64`) as
  a script that does not exist; a target with no interpreter word runs as it always did.
- **An executable script hands over by its shebang.** An agent started as a console script
  (`-- ./myagent`) rather than as `python …` is run by the interpreter its shebang names —
  including `#!/usr/bin/env python3` — so a console-script agent in a project's environment keeps
  its dependencies too. A shebang naming this same interpreter, and a non-executable file, are
  unchanged. **What changes for a caller:** an executable whose shebang names another Python used
  to run in this command's interpreter and fail to import the project's packages; it now runs in
  the interpreter the shebang names.
- **A runner in the first position is refused** (`64`): `-- uv run app.py`, `-- poetry run app.py`
  and their kind start an interpreter the boundary is not in, so handing the runner over would
  govern nothing. The refusal names the two spellings that work — name the interpreter, or ask the
  runner for it once. Before, `uv` was reported as a script that does not exist.
- **`instrument verify` matches a run's records by a correlation it stamps, not by their
  connection.** A program that makes two effects of different kinds is two asks, and the shipped
  boundary holds one connection per grant, so its records span two connections. They are still one
  run's, told so by a per-run token the verifier stamps on every ask and the plane records on the
  effect (`correlation_source: boundary_supplied`). **The defect this fixes:** such a run reported
  the second effect `unjudged` and exited `7`; it now verifies clean. The token also tells a
  concurrent same-account run's records apart, which the connection check could not, and it holds
  the first record as well as the rest. Needs the boundary distribution that stamps it, the one
  after 0.2.0.
- **The `unjudged:` line names the reason the run actually recorded**, one per distinct cause,
  rather than always saying an effect named a start file. A count made of a damaged range, an
  interrupted walk, another execution's record or an uninterposed path now reads as what it was.
- `docs/PACKS.md` records, with the evidence, why no convenience pack for `requests`, `httpx`,
  `os.system` or a Postgres driver is shipped — a limit of the verifier, not of the classification.
  The verifier confirms an effect from a distinct CPython audit event and shares no state with the
  engine; `requests`/`httpx`/Postgres emit nothing distinct from `socket.connect`, and `os.system`'s
  module is `os`, which the engine imports throughout, so a pack for it would make the engine-
  agnosticism guard read every `import os` as a special case. Each could be governed by hand against
  `sayfirst-boundary`; none can be shipped as a verifiable pack without weakening a guard.
- **`instrument run --follow-children`** installs the boundary in the Python children the program
  spawns with its environment, before the child's code runs, so a program that starts workers or
  tools of its own has their effects governed too — and a grandchild started the same way. It works
  by a `sitecustomize` on the child's import path (`src/sayfirst_cli/instrument/follow.py`), needs
  this client installed in the interpreter the children run, and fails a child **closed** once the
  bootstrap runs: a child that cannot install the boundary raises before its program runs, and a
  child whose daemon is unreachable fails at the ask exactly as the parent does. A child the
  bootstrap never reaches is not followed and runs as it would without the flag: one started with
  `-S`, `-I` or `-E`, or given a `PYTHONPATH` of its own. It is `run`'s flag, not `verify`'s: a spawned
  child is a separate process the single-process proof cannot see (`harness.py` counts such a child
  as coverage it could not judge), so following would govern what the proof misses.
- With no `--socket` and nothing at the default address, `instrument run` says which address it
  looked at before the program starts. Nothing else about that run changes: a program that asks
  nothing still runs, and an effect a pack names still fails closed, as the program's own
  exception.
- The quickstart is three commands, and the page is a transcript of them.
- **`instrument run` ends with the outcome's own status when the program does not handle it.** A
  boundary outcome the program lets escape — denied, suspended, refused, could not ask — used to
  end the run as any uncaught exception does, with the interpreter's `1`, which is this client's
  « deny » for all four. The traceback is still the program's; the status is now `1`, `5`, `3` or
  `4`. A program that catches the outcome and exits on its own still ends with its own status.
- **`instrument verify` asks for every effect.** The boundary in front of a verified program holds
  no grant, so an identical effect repeated while a grant lived — answered with nothing asked and
  nothing recorded — is no longer reported `ungoverned` and stopped (`6`). `instrument run` still
  holds its grants (article 10).
- **`instrument verify` counts one spawn once.** `subprocess.Popen` creates its process through
  `os.posix_spawn` or, from Python 3.14, `_posixsubprocess.fork_exec`, both paths the subprocess
  pack names as not interposed, so one governed spawn was reported with an unjudged effect and
  `7`. A point may now name, among its `uninterposed_events`, the `inner_events` its own call
  raises; such an event is paired with the call it judged when it is that thread's very next event
  and carries the same argument vector, and is counted otherwise. The subprocess pack also names
  `_posixsubprocess.fork_exec`, which is how `multiprocessing` starts a process by default on Linux
  from 3.14, so such a start is counted instead of passing unseen.
- **`instrument verify` answers `3` for a chain read the plane refused**, as every other command
  does, rather than `4`; and `7` rather than `4` when it never saw the program's own code start,
  since the plane had been asked. `docs/PACKS.md` lists the statuses.
- **Every connection is bounded.** `ask`, every read and the verifier's chain walk wait at most
  five seconds for an answer; a far end that accepts and never answers is « could not ask » (`4`)
  instead of a command that hangs. A named `--socket` is made absolute once, so a program that
  changes directory asks the daemon it was pointed at (with the contract distribution of this
  release).
- **Smaller corrections.** A uid with no account name is spelled `user:<uid>`, as the daemon names
  it, instead of ending `instrument run` in a traceback; an `ask` answer nested past the reads'
  depth bound is an answer this client could not read (`4`), not a traceback; `evidence export`
  that cannot write its bundle says « could not save » (`7`); on Python 3.14, an `--out` path this
  client cannot look at is still refused (`64`) before anything is asked, and an entry
  `evidence exports` cannot look at is still « could not check » (`7`); `approvals` names the
  person who acted; `packs check` refuses a pack whose `uninterposed_events` or `inner_events` the
  verifier would refuse.
- **Interpreter hand-over.** A script whose shebang names a Python that is not there is refused
  (`64`) instead of being run by this client's own interpreter; an interpreter newer than the lent
  packages declare (3.15 and later) is refused; `--follow-children` under a named interpreter that
  does not have this client installed is refused, where every Python child used to die at
  start-up; and under `PYTHONSAFEPATH` the head of the import path is left as the interpreter gave
  it, where the launcher used to replace an entry of the person's own.
- The full gate runs on Python 3.12, 3.13 and 3.14, the interpreters `requires-python` admits.

- Every commit of a change is read for its sign-off on every pull request, and one that carries
  none is refused by name. A range that cannot be read is refused too, rather than reported as
  passing.
- The publication checklist carries every act the constitution names, in the order they are
  performed, and a guard fails when one of them stops being a line of it. The security policy says
  which of article 0's two paths this repository is published by: a fresh repository, never a
  change of visibility.
- The gate reduces on a machine with no contract instead of failing there. A test that asks for a
  command only when it runs — this client imports a verb when it dispatches it — is now stood
  down by name and counted, the way a module that could not be imported already was, and a run
  with the contract hidden is required to come back green rather than merely to collect.
- One of the two gate legs runs, decided by whether the control plane's public repository can be
  read at the tag this client pins. The question is asked once, of the remote, with no credential;
  a leg reporting that the contract is absent no longer runs on a machine where it is not.

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
