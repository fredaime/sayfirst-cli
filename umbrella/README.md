<!-- SPDX-License-Identifier: Apache-2.0 -->
# `sayfirst` — ask before you act

This distribution is the product, installed whole. It installs no code of its
own: it depends on the three distributions that carry the three commands, each
at this same version, and names those commands so that one install exposes
them.

```console
$ uv tool install sayfirst
$ sayfirst-daemon up --quickstart
$ sayfirst instrument run --pack subprocess --scope local -- python3 my_agent.py
```

| Command | What it is | The distribution that owns it |
|---|---|---|
| `sayfirst` | the product client: ask, trace, explain, evidence, approvals, instrument, packs | `sayfirst-cli` |
| `sayfirst-daemon` | the control plane's daemon: `serve`, `up --quickstart`, `down` | `sayfirst-control-plane` |
| `sayfirstd` | the daemon's operator surface: `status`, `whoami`, `plugins`, `conformance` | `sayfirstd` |

The client's [`QUICKSTART.md`](https://github.com/fredaime/sayfirst-cli/blob/main/QUICKSTART.md)
walks all of it from the second command on; its first command is the
three-package install that this distribution replaces. Each command is
documented where it is declared.

## What it is not

- **Not the client alone.** A program that only asks, reads and verifies needs
  `sayfirst-cli`, which brings the contract and the boundary and never the
  daemon. This distribution brings the daemon on purpose.
- **Not a place where anything is decided or documented.** Every sentence
  about what the product does, and does not do, is on the pages of the
  distributions above.

## Coming from the three-package install

Before this distribution existed, the same three commands were installed as
one tool named `sayfirst-cli`. `uv` refuses to write a command another tool
already owns, so stop the quickstart daemon, if `up` started one, and remove
the tool first. If the three commands were installed as three tools instead,
all three have to go, and the second line is
`uv tool uninstall sayfirst-cli sayfirst-control-plane sayfirstd`.

```console
$ sayfirst-daemon down
$ uv tool uninstall sayfirst-cli
$ uv tool install sayfirst
```

None of these lines removes the policy, the configuration or the evidence
under `~/.sayfirst/quickstart`: they are kept, and the next
`sayfirst-daemon up --quickstart` finds them.

`uv`'s refusal offers `--force`. It installs this tool over the old one and
leaves the old one installed; removing `sayfirst-cli` afterwards removes the
three commands again, and `uv tool install --reinstall sayfirst` puts them back.

## Removing it

Stop the quickstart daemon first, if `up` started one. Once the commands are
gone, nothing is left to stop it with:

```console
$ sayfirst-daemon down
```

Then, as a tool, remove the tool: `uv tool uninstall sayfirst`. In an
environment of your own, remove the product whole, since this distribution and
the three it depends on each declare the commands:

```console
$ pip uninstall sayfirst sayfirst-cli sayfirst-control-plane sayfirstd sayfirst-contract sayfirst-boundary
```

Removing `sayfirst` alone from such an environment removes the three commands
and leaves the distributions that own them installed, without their commands.
`pip install --force-reinstall --no-deps` of an owner puts its command back.
