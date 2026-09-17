# SPDX-License-Identifier: Apache-2.0
"""A governed program, a pack that governs it, and the way a person runs both.

Every `instrument run` here goes through a real process. Two reasons, and both
are properties of the thing under test rather than convenience: the
interposition is process-scoped by design, so an in-process run would leave a
wrapped attribute behind for the rest of the session; and the launcher's whole
claim is that it does not own the program's exit code, which only a process can
show.

**And through the console script, never `python -m sayfirst_cli.main`.** That
form puts the working directory on the import path as a side effect of how the
interpreter starts, and the working directory is where a governed program's own
modules live — so it silently supplies the very thing the launcher has to supply
itself, and every test of it passes while the shipped command cannot run a
program of more than one file. It is the command a person types or it proves
nothing about the command a person types.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn, UnixStreamServer

from sayfirst_contract.generation import CONTRACT_GENERATION

REPOSITORY = Path(__file__).resolve().parents[1]

#: The console script this distribution installs, beside the interpreter running
#: these tests. `pyproject.toml` declares it as `sayfirst = sayfirst_cli.main:run`.
CONSOLE_SCRIPT = Path(sys.executable).parent / "sayfirst"

#: A program that spawns something, and nothing else. It catches nothing: a
#: refusal from the boundary is its own exception to propagate.
SPAWNING_APP = """\
import subprocess

subprocess.run(["true"], check=True)
"""

#: The execution module of a pack that governs spawning a process. It binds the
#: call's arguments to the original signature rather than guessing at positions,
#: and digests only what the manifest declares (article 11).
SPAWN_INTERPOSE = '''\
# SPDX-License-Identifier: Apache-2.0
"""Ask before a process is spawned, with the arguments the manifest names."""

import inspect


def wrap(original, capability, boundary):
    signature = inspect.signature(original)

    def wrapper(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        arguments = {"args": [str(item) for item in bound.arguments["args"]]}
        with boundary.request(capability, arguments):
            # Nothing is recorded here: a process that has just been spawned has
            # no outcome yet, and the boundary records that absence honestly
            # rather than this pack inventing a digest for it (article 2).
            return original(*args, **kwargs)

    return wrapper
'''

#: A two-file program: the module a person actually writes imports the module
#: beside it. One file proves nothing about the import path, because a main
#: script is found by name and never imported.
SIBLING_APP = """\
import subprocess

import helper

print("helped by", helper.NAME)
subprocess.run(["true"], check=True)
"""

#: The same program named as a module, for the `-m` form.
SIBLING_MODULE_APP = """\
import helper

print("helped by", helper.NAME)
"""

#: A program that imports the module beside it and spawns nothing, so it needs
#: no daemon to say whether the import path was arranged.
SIBLING_ONLY_APP = """\
import helper

print("helped by", helper.NAME)
"""

HELPER = """\
NAME = "the-sibling"
"""

SPAWN_MANIFEST = """\
[pack]
name = "process-effects"
classification = "convenience"
classified_on = 2026-09-14

[[point]]
module = "subprocess"
attribute = "Popen"
capability = "process.spawn"
digest = ["args"]
audit_event = "subprocess.Popen"
"""

SPAWN_NOTE = """\
<!-- SPDX-License-Identifier: Apache-2.0 -->
A convenience pack written for one test: a competent engineer would rebuild it
in a day from public documentation, which is article 9's own test for the class.
Classified 2026-09-14.
"""


def plant_spawn_pack(root: Path, *, name: str = "pack") -> Path:
    """A valid pack that governs spawning a process, outside any governed tree."""
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "pack.toml").write_text(SPAWN_MANIFEST, encoding="utf-8")
    (directory / "interpose.py").write_text(SPAWN_INTERPOSE, encoding="utf-8")
    (directory / "NOTE.md").write_text(SPAWN_NOTE, encoding="utf-8")
    return directory


def instrument(
    *argv: str, cwd: Path | None = None, env: Mapping[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run `sayfirst instrument …` the way a person runs it, and report what a shell sees."""
    assert CONSOLE_SCRIPT.is_file(), (
        f"{CONSOLE_SCRIPT} is not installed. These tests run the console script rather "
        f"than `python -m sayfirst_cli.main`, because that form would supply the working "
        f"directory as the head of the import path and hide whether the launcher supplies "
        f"it. Install this distribution into the interpreter running the tests."
    )
    return subprocess.run(
        [str(CONSOLE_SCRIPT), "instrument", *argv],
        cwd=str(cwd or REPOSITORY),
        capture_output=True,
        text=True,
        timeout=120,
        env=None if env is None else dict(env),
    )


def tree_shape(tree: Path) -> dict[str, str | None]:
    """Every file under a tree: its relative path, and its content unless it is bytecode.

    A `.pyc` carries the source's modification time in its header, so two runs
    of one program never write byte-equal caches and comparing their bytes would
    be comparing clocks. Its PRESENCE is the fact worth comparing — a cache that
    appeared under one run and not the other is a trace one of them left — so
    the bytes are recorded as `None`, visibly, rather than quietly excused.
    """
    shape: dict[str, str | None] = {}
    for item in sorted(tree.rglob("*")):
        name = str(item.relative_to(tree))
        if item.is_dir():
            # A directory that appeared is a trace too, even an empty one.
            shape[name + "/"] = None
            continue
        shape[name] = (
            None if item.suffix == ".pyc" else hashlib.sha256(item.read_bytes()).hexdigest()
        )
    return shape


def plain_environment() -> dict[str, str]:
    """This environment with nothing in it that would suppress a bytecode cache.

    Both runs of the comparison need the same answer to « may I write a cache »,
    and a host that had set it would make the whole comparison vacuous: two
    clean trees are equal for a reason that has nothing to do with the engine.
    """
    environment = dict(os.environ)
    environment.pop("PYTHONDONTWRITEBYTECODE", None)
    return environment


def plant_two_file_program(root: Path, name: str) -> Path:
    """A tree holding a program and the module it imports, which is the real case."""
    tree = root / name
    tree.mkdir(parents=True)
    (tree / "script.py").write_text(SIBLING_APP, encoding="utf-8")
    (tree / "helper.py").write_text(HELPER, encoding="utf-8")
    return tree


def ungoverned(tree: Path) -> subprocess.CompletedProcess[str]:
    """The same program, run the way it runs when nobody is governing it."""
    return subprocess.run(
        [sys.executable, "script.py"],
        cwd=str(tree),
        capture_output=True,
        text=True,
        timeout=120,
        env=plain_environment(),
    )


#: An execution module that asks before the call and digests the first argument,
#: for a point whose original takes something other than a command line. The
#: spawn pack's own wrapper binds `args` by name and would refuse anything else.
FIRST_ARGUMENT_INTERPOSE = '''\
# SPDX-License-Identifier: Apache-2.0
"""Ask before the call, with the first positional argument as the digest."""


def wrap(original, capability, boundary):
    def wrapper(*args, **kwargs):
        with boundary.request(capability, {"args": [str(item) for item in args[:1]]}):
            return original(*args, **kwargs)

    return wrapper
'''


def plant_pack(
    root: Path,
    *,
    name: str,
    module: str,
    attribute: str,
    capability: str,
    interpose: str = SPAWN_INTERPOSE,
    audit_event: str | None = None,
) -> Path:
    """A pack directory with one point, for the refusals that need a bad one.

    `audit_event` defaults to the module and attribute joined, which is how
    CPython spells the event for most of the operations a pack wraps. A test
    about the verifier's own hook supplies it instead: the interpreter's own
    events — the ones it raises for reading a file or executing code — are
    named by one bare word, and those are the events whose exclusion rules the
    harness has to get right.
    """
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "pack.toml").write_text(
        "[pack]\n"
        f'name = "{name}"\n'
        'classification = "convenience"\n'
        "classified_on = 2026-09-14\n"
        "\n"
        "[[point]]\n"
        f'module = "{module}"\n'
        f'attribute = "{attribute}"\n'
        f'capability = "{capability}"\n'
        'digest = ["args"]\n'
        f'audit_event = "{audit_event or f"{module}.{attribute}"}"\n',
        encoding="utf-8",
    )
    (directory / "interpose.py").write_text(interpose, encoding="utf-8")
    (directory / "NOTE.md").write_text(SPAWN_NOTE, encoding="utf-8")
    return directory


class _Server(ThreadingMixIn, UnixStreamServer):
    daemon_threads = True


@contextmanager
def recording_daemon(socket_path: Path) -> Iterator[tuple[Path, list[dict[str, object]]]]:
    """A daemon that answers `allow` and keeps every ask, so the wire can be read.

    The contract's fake answers by scenario and never hands back what it was
    asked, so it cannot say whether the scope a person typed is the scope that
    went out. This one records the request documents verbatim. It decides
    nothing and holds no policy: it is a listener with a notebook.

    It answers with a plain decision document rather than a stream, so no grant
    is minted and every act asks again — which is what a test reading the wire
    wants.
    """
    asks: list[dict[str, object]] = []

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            document = json.loads(self.rfile.read(length) or b"{}")
            asks.append(document)
            answer = {
                "contract_generation": CONTRACT_GENERATION,
                "authority": "authoritative",
                "decision_ref": f"decision-{len(asks)}",
                "scope": document.get("scope", "local"),
                "capability": document.get("capability", "example.effect"),
                "outcome": "allow",
                "reason": "policy_allows",
                "policy_version": None,
                "approval_ref": None,
                "decided_at": "2026-09-15T00:00:00+00:00",
                "correlation": None,
            }
            body = json.dumps(answer).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = _Server(str(socket_path), _Handler)
    os.chmod(socket_path, 0o700)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield socket_path, asks
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        socket_path.unlink(missing_ok=True)
