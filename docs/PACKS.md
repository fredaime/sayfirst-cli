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

A pack is **designated by path**. `sayfirst instrument run --pack DIR …`
names the directory directly, the same way a person names a file to run. There
is no search path this client consults on its own, no default set of packs it
installs unless told to, and no name a pack is resolved from — `--pack` takes
a path and nothing shorter. `sayfirst packs list` and `sayfirst packs check`
read the packs this distribution ships beside it, but neither is consulted by
`instrument run`, which reads only the paths a person types.

## The packs this distribution ships

| name | capability | classified | what it governs |
|---|---|---|---|
| `subprocess` | `process.spawn` | 2026-09-15 | `subprocess.Popen` — and, because `subprocess.run`, `subprocess.call` and `subprocess.check_output` all spawn through the module's own `Popen`, all four call shapes with it |
| `http-client` | `net.egress` | 2026-09-15 | `urllib.request.urlopen` — the one function every scheme `urllib.request` handles goes through (`http`, `https`, `file`, `data` alike), so `file:` and `data:` reads are asked under this capability too, since the interpreter offers no narrower seam; the URL in the digest is what distinguishes them. The capability names the effect — a request leaving the process — and borrows no segment from the module or the attribute. The verifier keys on `urllib.Request`. |
| `database` | `database.open` | 2026-09-15 | `sqlite3.connect` — opening a database. The verifier keys on `sqlite3.connect`. |

This table is held against the distribution by
`tests/test_packs_shipped.py`: one row per pack that ships, no row for a pack
that does not, and the classification date read from each pack's own
`pack.toml`. A table maintained by hand is a claim; this one fails the gate
when it stops matching.

Each is installed the same way: `sayfirst instrument run --pack
<path-printed-by-'sayfirst packs list'> …`. `sayfirst packs check PATH` reads
one pack the way the engine will and says whether it is valid, without running
anything. `sayfirst packs list` prints one line per pack — `<name>
<capability…> <path>` — and a pack whose manifest does not read is named on
the error stream with the member and the rule it broke, the rest of the list
is printed anyway, and the command exits `64`. It never omits a broken pack in
silence, and it never ends in a traceback.

## Verifying

`sayfirst instrument verify --pack DIR … --socket P --scope S -- <program>`
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

A run can also report **no verdict at all**, and exits `4` when it does: the
chain could not be read — before the program started, or while it ran — or the
verifier never saw the program's own code start (a target the interpreter runs
from bytecode with no source beside it). None of these is a verdict about the
program, and none is rendered as one; each carries its own problem code and its
own sentence, because « this run established an absence », « this run never
began watching » and « the chain could not be read » are different facts. The
harness says which of its own endings happened in a file of its own, so the
answer is never chosen by the number the verified program happened to exit with.

A report that arrives and cannot be read exits `7`, the code for a check that
could not conclude: the findings exist and this client could not read them,
which is not a program found wanting.

**And `64` for the invocation's own mistakes**, which are not outcomes at all:
an invocation the harness refused before it began — a target that names no
program, a pack that will not read, a point the engine will not install — and a
profile this command refuses before a second interpreter is started. No question
was ever put, so none of these is a verdict, and each is the same `64`
`sayfirst instrument run` gives the very same mistake. That is the whole of what
this verb assigns: `0`, `6`, `7`, `4`, `64` — a usage error is the parser's `2`, as
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

## No registry, no marketplace, no signature scheme

There is no registry, no marketplace and no signature scheme. This statement
is to be re-examined by **2027-03-14**; past that date the packaging test
fails until it is renewed or replaced.

statement-reexamined-by: 2027-03-14
