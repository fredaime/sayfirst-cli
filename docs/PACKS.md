<!-- SPDX-License-Identifier: Apache-2.0 -->
# Packs — article 9's convenience packs, as this distribution ships them

## What a pack is

A pack is a directory carrying three required files: `pack.toml` (the manifest — the
pack's own name, its classification, and one `[[point]]` per attribute it
interposes: the module, the attribute, the capability it names, the call
arguments its digest covers, and the audit event a verifier watches for),
`interpose.py` (the local execution module — one function, `wrap(original,
capability, boundary)`, that returns the replacement for the named attribute),
and `NOTE.md` (the classification note: why this is a convenience pack rather
than something article 9 keeps out of the open core, and when it was
classified). `src/sayfirst_cli/instrument/manifest.py` requires all three and
refuses a directory missing any of them, naming the member and the rule.

**A capability is judged by two rules, and only one of them is this client's.**

**The spelling is the control plane's rule.** What a capability may look like is
published in the ask-request schema (`decision-ask-request`, the document the
daemon validates a question against), and this client reads the rule off that
schema rather than
keeping a copy of it: lower-case dotted words, letters and digits only, no
underscore and no capital, one to a hundred and twenty-eight characters. A
spelling the schema refuses is a question that could never be asked, so a pack
declaring one is refused before anything runs, and the refusal quotes the
schema's own pattern rather than paraphrasing it. A copy kept here once was
wider than the original and a shipped pack was caught by it, which is why the
rule is read and not restated.

**Naming the effect rather than the library is this client's own rule.** No
segment of a capability may be a segment of the module path it is declared on,
nor the attribute it wraps, compared with the case folded on both sides. So
`process.popen` declared on `subprocess.Popen` is refused, and so is
`database.connect` on `sqlite3.connect`: each borrows a segment from the point
it governs. Name the effect instead — `process.spawn`, `database.open`,
`net.egress` — which is the rule working rather than the rule being awkward.
`src/sayfirst_cli/instrument/manifest.py` enforces both, the schema's first,
and it says why a comparison of whole dotted spellings could never have fired
for the single-segment modules every one of these packs declares. The two are
independent and both are needed: the schema's shape admits a single bare word,
and this rule is what stops that word being the library's own name.

Anything else in the directory is **ignored**, and that is the reader's rule
rather than an oversight: the three are required, nothing else is read, and
nothing else is refused. A `__pycache__` Python left there, a `README`, a
helper module beside `interpose.py` — none of them makes the directory
invalid. (Loading a pack does not itself write a `__pycache__` into it: the
engine loads `interpose.py` through a loader with the bytecode write taken
out, so a pack on a read-only path works and a pack on a writable one is left
as it was found.)

A pack is **designated by the person who runs it**, in one of two spellings,
and which one applies is decided by the spelling alone — before the file system
is looked at, so the same words mean the same thing in every directory.

* **A path is a directory.** A designation with a path separator in it — and
  `.` and `..` — names the directory directly, the same way a person names a
  file to run: `--pack ./own-pack`, `--pack /srv/packs/own-pack`.
* **A bare word is the name of a pack this distribution ships**:
  `--pack subprocess`, `--pack http-client`, `--pack database`. It is looked up
  in one place, the package data installed beside this client — the set
  `sayfirst packs list` prints — and a word that names nothing shipped is
  refused, saying what is shipped and how a directory is spelled.

That is a designation and not a registry, because everything a registry would
be is absent on purpose. There is no search path: one location is read and it
is not configurable — no environment variable, no file, no directory of the
user's. There is no fallback between the two readings: a bare word is **never**
tried as a directory of the working directory, so a directory somebody left
beside a program cannot become the code that runs in front of it, and a path is
never tried as a name. There is no default set: a pack nobody designated is not
installed. And there is no name anybody else can publish under: the set is
closed by what this distribution carries, and a pack of one's own is designated
by its path. `src/sayfirst_cli/instrument/designation.py` is the whole of the
rule, and `tests/test_pack_designation.py` holds both halves and the two ways
they could leak into each other.

(This replaces an earlier, stricter statement — « `--pack` takes a path and
nothing shorter » — under which the path of a shipped pack had to be copied out
of `sayfirst packs list`: an installation's site directory typed by hand. What
that statement protected is kept word for word above; what it cost was that the
first command a person ran named a directory inside somebody's environment.)

## The packs this distribution ships

| name | capability | classified | what it governs |
|---|---|---|---|
| `subprocess` | `process.spawn` | 2026-09-15 | `subprocess.Popen` — and, because `subprocess.run`, `subprocess.call` and `subprocess.check_output` all spawn through the module's own `Popen`, all four call shapes with it |
| `http-client` | `net.egress` | 2026-09-15 | `urllib.request.urlopen` — the one function every scheme `urllib.request` handles goes through (`http`, `https`, `file`, `data` alike), so `file:` and `data:` reads are asked under this capability too, since the interpreter offers no narrower seam; the URL in the digest is what distinguishes them. The capability names the effect — a request leaving the process — and borrows no segment from the module or the attribute. The verifier keys on `urllib.Request`. **One call is not always one request**: an address that answers `302` makes a second, and the redirect handler makes it through the opener it is attached to rather than by calling `urlopen` again — so for the length of one governed call the opener's own `open` is asked about too, once per request, with the address that hop resolved. That is the arithmetic the verifier already does, one consultation per `urllib.Request`, so a redirect of any length, and one that moves host or scheme, is asked about as many times as the interpreter reports it. A request made on an opener directly, outside any `urlopen`, is not asked about — the verifier watching the same events says so as a finding rather than this pack pretending otherwise. |
| `database` | `database.open` | 2026-09-15 | `sqlite3.connect` — opening a database. The verifier keys on `sqlite3.connect`. |

This table is held against the distribution by
`tests/test_packs_shipped.py`: one row per pack that ships, no row for a pack
that does not, and the classification date read from each pack's own
`pack.toml`. A table maintained by hand is a claim; this one fails the gate
when it stops matching.

Each is installed the same way: `sayfirst instrument run --pack <name> …`.
`sayfirst packs check PACK` takes the same two spellings `--pack` does, reads
that one pack the way the engine will and says whether it is valid, without
running anything. `sayfirst packs list` prints one line per pack — `<name>
<capability…> <path>` — and a pack whose manifest does not read is named on
the error stream with the member and the rule it broke, the rest of the list
is printed anyway, and the command exits `64`. It never omits a broken pack in
silence, and it never ends in a traceback.

## Verifying

`sayfirst instrument verify --pack PACK … --scope S -- <program>`
proves one thing about one run: **every effect of a kind a designated pack
names was preceded by a decision.** It proves it from two sources and no
third — the events the interpreter itself reports (`sys.addaudithook`) and the
scope's evidence chain as the daemon recorded it. It shares no state with the
engine, on purpose: a proof that trusts the thing it is proving is not a
proof. Consequently the verdict does not change with how a decision came to be
in the chain, and `--ungoverned` — which runs the program with nothing in
front of it — is a supported way to ask the chain alone.

The program runs in a process of its own, under an audit hook that raises when
an effect arrives that the chain cannot account for. The raise aborts that
effect inside the program rather than reporting afterwards that it had already
happened. A hook cannot be removed from a running interpreter, which is why
this is the verifier and not the engine: article 9 asks the primary mode to be
reversible, and `instrument run` is.

**Three verdicts, and one of them is an absence.** (Written out rather than
tabulated: the only table in this document is the shipped-packs table above,
which `tests/test_packs_shipped.py` reads by walking the document's rows.)

* `governed` — the effect happened and a decision preceded it. The command
  exits `0` only when every point of every designated pack is this.
* `ungoverned` — the effect happened and no decision preceded it. Exit `6`: a
  finding this client made, never a denial the plane gave (article 1).
* `not-exercised` — this run never walked the path. Exit `7`: a check that
  could not conclude.

**And one count that is not a verdict.** The interpreter's own reads of the
program's start files, before the program's code runs, are the hand-off's and
are not judged. Should an effect on a point still be excluded by that rule
after the program started — a program that opens one of its own start files,
or writes to a name derived from its own bytecode cache — the report says so
on that point as `unjudged: N`, the judged verdict stands beside it, and the
run exits `7`: an effect this proof did not see is never a pass, with the one
exclusion stated next.

**With one exclusion, stated rather than left implicit.** Handing a program over
by a dotted `-m` name means resolving it one segment at a time, and running each
package's `__init__` on the way; between the end of one of those and the start of
what follows it, the launcher is still locating the program and everything that
happens is attributed to the hand-off — so an effect a program makes from inside
that stretch, from a thread or an import hook of its own, is neither judged nor
counted, and leaves no `unjudged` behind it.
`src/sayfirst_cli/instrument/launch.py` records the stretch, its measured width
and why it is measured rather than guarded.

A run can also report **no verdict at all**: the chain could not be read —
before the program started, or while it ran — and it exits `4`; or the
verifier never saw the program's own code start (a target the interpreter runs
from bytecode with no source beside it), and it exits `7`, because the plane
was asked and what could not be done was the watching. None of these is a
verdict about the program, and none is rendered as one; each carries its own
problem code and its own sentence, because « this run established an
absence », « this run never began watching » and « the chain could not be
read » are different facts. The harness says which of its own endings happened
in a file of its own, so the answer is never chosen by the number the verified
program happened to exit with.
A chain read the control plane **refused** — a scope it will not read, a
principal it does not admit — exits `3` instead, as it does for every other
command of this client: the plane was asked, and it said no. The harness writes
the class of the problem beside its code, because the same code is minted on
both sides of the wire and only the value says which side it came from.

A report that arrives and cannot be read exits `7`, the code for a check that
could not conclude: the findings exist and this client could not read them,
which is not a program found wanting.

**And `64` for the invocation's own mistakes**, which are not outcomes at all:
an invocation the harness refused before it began — a target that names no
program, a pack that will not read, a point the engine will not install — and a
profile this command refuses before a second interpreter is started. No question
was ever put, so none of these is a verdict, and each is the same `64`
`sayfirst instrument run` gives the very same mistake. That is the whole of what
this verb assigns: `0`, `6`, `7`, `3`, `4`, `64` — a usage error is the parser's `2`, as
the README says of every command — and `tests/test_packs_shipped.py` holds this
section against `exit_codes.CODES` in both directions.

**`not-exercised` is never a pass.** A path a run did not walk is not a path
proven safe, and rendering it green would be the false all-clear article 2
forbids. It is a third value where a reader might expect two, and it is said
in words as well as in the code.

Each line of the output is `<verdict> <pack> <module>.<attribute>
<capability> events=<n>`, followed by `inspected:` — the packs whose points
were actually watched for — and `target exit:`, the program's own ending,
which is a fact in the report and never this command's exit code. Under
`--json` the whole report is the `result` of the usual envelope. The program's
own output, on both of its streams, arrives on the error stream — so the
envelope goes to **stdout**, on every path, findings or none: a program can
print a problem object of its own on the stream it was given, and a machine
reader looking for the first `{` would find the program's.

**Where the anti-vacuity gate runs.** Article 9 asks the verifier to run
"against every shipped pack in the public gate, failing unless it inspected
each one", so `inspected` is read off the points the harness watched for
rather than off the command line. The assertion that the set equals the set of
shipped packs — against the real daemon, with a real chain — is the control
plane's end-to-end gate, not this repository's: the contract's fake serves
placeholder evidence pages by its own admission, so a run against it can prove
the hand-off and the report's shape and nothing about a chain.

## Matching

A verification is two sources against each other: the events the interpreter
reported, and the records the chain holds. **Matching** is the rule that says
which record answers for which event, and it is the rule the whole verdict rests
on — a verifier that accepts the wrong record has proven that a decision exists
somewhere in the scope, never that one preceded the effect it watched.

A record answers for an observed effect when all of the following hold, and it
is stepped over when any of them does not.

* It is an entry of kind `effect`, of the capability the point declares, whose
  outcome the plane recorded as `allow`.
* It sits **after the position the chain had before the program started**. A
  record already there when the run began is not a record this run produced.
* It has not already been **spent**. One recorded decision answers for one
  effect and never for a second — and what is spent is what was *used*, never
  what a walk stepped over on the way. A walk that spent what it skipped made
  every record behind the one it took unreachable, so an effect whose decision
  was sitting in the chain was reported as a finding against it; the chain is
  written in decision order and a program runs in execution order, and the two
  are not the same order. **Which is why a verifying run holds no grant.**
  Under `instrument run` the boundary keeps what it was granted (article 10),
  and an identical effect repeated while that grant lives is answered by it
  with nothing asked and nothing recorded. Under `verify` the boundary in front
  of the program asks for every effect, so every effect has a record of its
  own: a program that spawns the same command twice is two decisions there,
  and one there would read the second spawn as ungoverned.
* It was **recorded for the account this process runs as**. Identity is the
  operating system's (article 6): the daemon builds a principal from the peer
  credential of the connection that asked, and the peer of a governed program's
  boundary is the process being verified. A record of another principal is
  somebody else's decision, it answers for nothing here, and it is said on the
  error stream so that a reader who can see an allow in the chain is not left
  wondering why it answered for nothing.
* It comes out of a range **the chain's own verification reports `intact`**.
  The daemon serves its reading of the chain beside the page; three of the four
  conditions it can report are a break, a declared gap and « could not tell »,
  and a record read out of any of them is evidence the writer of the chain
  declined to stand behind. Taking one is a claim stronger than the evidence
  held (article 2), so it is not taken, and the effect is **not judged** rather
  than found against: a damaged chain is not an established absence.
* Where this run's own boundary is what asked — the governed hand-off, which is
  the shipped mode — it carries this run's **correlation**: a token the verifier
  generates before the program starts and the boundary stamps on every ask, which
  the plane records on the effect (`correlation_source: boundary_supplied`). A
  record without it, or with another value, is another execution's and answers
  for nothing here — the first record is held to the token exactly as every later
  one is. The boundary holds one connection per grant, so a run that asks about
  several kinds of effect spans several connections; the correlation is one value
  for the whole run and does not, which is why the run is matched by it and not by
  a connection. Under `--ungoverned` the program runs with nothing in front of it
  and the chain alone answers, so the records were written by another execution by
  construction and no correlation is required of them.

**What matching does not establish, stated rather than implied.** It does not
compare the arguments of the observed call with the digest the record carries.
Two effects of one kind, by one principal, in one run are therefore not told
apart: a record this run produced can, in principle, be a decision that covered a
different call of the same kind. Which arguments identify an
effect is the pack's declaration and the boundary's digest (article 11), and a
pack publishes no way to render them for anything but its own wrapper — so a
verifier that computed a digest of its own would be a second policy, agreeing
with the first on the day it was written and drifting afterwards, and its
disagreements would arrive as findings nobody made. Closing this needs the pack
interface to publish the rendering, which is a change to what a pack is; until
it does, the limit is here in writing rather than hidden behind a green run.

## Coverage

A verdict is about the points a pack names. **Coverage** is about everything
else of that kind: whether the effects this run judged were all the effects of
that kind the run made.

Instrumentation can miss a call, and that limit is real, documented and
unchanged — a governed program *calls* the boundary, and a call that reaches
the world by some other route was never asked about (article 2). What changed
is the silence. An effect that took such a route used to be dropped, and the
point's verdict — earned by the calls that *did* go through the interposed
attribute — was then published as though it were the whole of the run: two
processes created, one decision, `governed`, exit `0`.

So a point may name, in its own `pack.toml`, the audit events by which an
effect of its kind reaches the world along a path **it does not interpose**:

    uninterposed_events = ["os.posix_spawn", "os.system"]

The declaration is the pack's because a pack is the one place a library's
vocabulary may be written down (article 4); the verifier holds none of its own
and watches for exactly what it was told. When such an event arrives while the
program is running, the run counts it on every point of that pack as an effect
it could not judge, says so on the error stream with the reason, and **lets the
call through**. A run holding one of those counts cannot answer `0`: it exits
`7`, the code for a check that could not conclude.

Letting it through is the point. `sayfirst instrument run` does not interpose
that path either, so a `verify` that aborted the call would be stricter than the
mode it exists to measure, and this software is a governance and observability
layer rather than a confinement mechanism. The honest report is « an effect of
this kind reached the world and this run could not judge it », not « this run
stopped it ».

**An interposed call can raise one of those events itself.** `subprocess.Popen`
creates the process it was asked for through `os.posix_spawn` whenever it can —
for an executable named with a directory, by default from Python 3.14 — and
otherwise through `_posixsubprocess.fork_exec`, which raises an event of its
own from Python 3.14. Both are paths the subprocess pack names, so one governed
spawn used to be reported as one judged effect plus one effect nobody judged,
and the run exited `7` for a program that did nothing around the pack. A point
therefore names, among its uninterposed events, the ones its own call raises:

    inner_events = ["os.posix_spawn", "_posixsubprocess.fork_exec"]

Such an event is not counted when it is **the very next event the same thread
raises** after the call the point judged and let through, and it carries as its
second argument the argument vector that call's event carried as its second —
the process `Popen` was asked for, against the process created beneath it.
Anything else is counted: another command, a second inner event, an inner event
raised after anything else the thread did. An inner event must be one the same
point names as uninterposed, and a pack declaring otherwise is refused.

One shape stays out of reach, and it is written here rather than hidden. Before
Python 3.14, `Popen` creates a process it cannot hand to `os.posix_spawn` with
no event at all; a program whose very next act after such a call is a direct
`os.posix_spawn` of **the same command** has that second process paired with
the first. It names the command the plane just allowed; it is still a second
process. On 3.14 the fork-and-exec raises its own event, which takes the pairing,
and the direct spawn is counted. That same event is also how `multiprocessing`
starts a process — by default on Linux from 3.14 — so the subprocess pack names
it as a path it does not interpose, and a process started that way is counted.
Before 3.14 it raises nothing and is not.

Two other things leave coverage incomplete, and both are counted the same way
and for the same reason.

* **A run that forked.** A fork copies the audit hook, the chain's position and
  every finding into a memory the process that writes the report cannot read.
  The child goes on being watched — it aborts an effect no record covers,
  exactly as the parent would — and then its observations end with it.
  Collecting them from the parent's side is not something this harness can do;
  saying that they are missing is, and a report that does not cover the whole
  run is not a pass. A child never writes the run's report or its outcome file:
  it holds the parent's paths, and a copy writing them would replace the
  parent's findings with its own view of a run the parent is still concluding.
* **A walk of the chain that did not reach the end.** `read_something` says a
  read was answered; it does not say the chain was read whole. With a
  continuation this client could not follow, a matching record on the page it
  never read is indistinguishable from no record at all — so the effect is
  aborted and counted, and no finding is published. `ungoverned` is a finding
  this client made, and incomplete information cannot support one.

Each of these is a count and a sentence, never a fourth verdict: every way of
spelling « could not judge » as one of the three words says something the run
did not measure, and the count is what refuses the pass.

## Why not `requests`, `httpx`, `os.system` or a Postgres driver

These are the libraries a convenience pack is most often wanted for, and they are
deliberately not shipped, for a reason in the verifier rather than in the
classification. The verifier confirms an effect from a **distinct CPython audit
event** and shares no state with the engine — a proof that trusts the thing it
proves is not a proof (§ Verifying). The shipped packs each key on such an event:
`subprocess.Popen`, `urllib.Request`, `sqlite3.connect`. `requests`
and `httpx` emit none of their own: their traffic reaches the interpreter only as
`socket.connect`, which every other socket also raises, so a pack keying on it
would claim urllib's connections and a second network pack's alike. A Postgres
driver is the same — `socket.connect`, plus a live server to exercise it.

`os.system` fails a different, equally real guard. It is a distinct audit
event (`os.system`), so the verifier could confirm it — but its MODULE is
`os`, which the engine itself imports and uses throughout. The rule that the
engine names no shipped pack's library (§ below; enforced by
`tests/test_engine_is_agnostic.py`, which walks the engine's own source) then
reads every `import os` in the engine as a special case for this pack's
library, and rightly so: a real special case for `os` would be invisible
beside them. Exempting `os` to ship the pack would blind that guard to the
most-used module in the engine, which is a security guard weakened to force a
convenience. So `os.system` stays a path the `subprocess` pack NAMES as one it
does not interpose and counts (§ Coverage), not a pack of its own.

Such a library can be **governed** (a pack wrapping `requests.Session.request`
asks before the call, and `instrument run` would honour it); it cannot be
**verified**, and article 9's gate requires the verifier to inspect every shipped
pack. Shipping one anyway would either fail that gate or make the verifier key on
a shared event — weakening the one-event-per-effect rule the whole proof rests
on. Closing this needs a verifier that can be given a library-specific
confirmation without trusting the engine for it, which is a change to what the
verifier is; until then, these are governed by writing the wrapper by hand
against `sayfirst-boundary`, not by a shipped pack.

## No registry, no marketplace, no signature scheme

There is no registry, no marketplace and no signature scheme. This statement
is to be re-examined by **2027-03-14**; past that date the packaging test
fails until it is renewed or replaced.

statement-reexamined-by: 2027-03-14
