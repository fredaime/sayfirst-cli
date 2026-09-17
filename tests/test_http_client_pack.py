# SPDX-License-Identifier: Apache-2.0
"""The `http-client` pack this distribution ships, proven the way it will run.

Article 9's second convenience pack, following `tests/test_subprocess_pack.py`'s
shape exactly: three levels, because the three things worth proving need
different instruments. `FakeBoundary` is driven in-process, because the outcome
digest `record_outcome` receives is never sent to a real daemon. `RefusingBoundary`
is driven the same way, over a recording stand-in for the real function, because
the one safety property this pack has — a refused ask never reaches the request
— is a statement about a call that must NOT happen, and only a recorded original
can say that it did not. `recording_daemon` is driven through the real console
script, because it is the only way to prove the capability and the arguments
actually reach the wire from a real governed process.

The one thing this pack needs that `subprocess`'s did not: something to open a
connection to. Every granted-path test here talks to a `http.server` this file
starts itself, on loopback, so nothing here reaches the network.

The doubles all three of these suites drive their packs against — `FakeBoundary`,
`RefusingBoundary`, `Spy` and the engine harness — are in `tests/pack_doubles.py`,
which records what three copies of them cost. What stays here is this pack's own:
its path, the call shapes it governs, and the capability its refusals name.
"""

from __future__ import annotations

import functools
import hashlib
import http.client
import threading
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from governed_programs import instrument, recording_daemon
from pack_doubles import FakeBoundary, RefusingBoundary, engine_fixture, installed
from pack_doubles import governed_by as _governed_by
from sayfirst_boundary import AskRefused, Denied, Suspended

from sayfirst_cli.instrument import manifest
from sayfirst_cli.instrument.engine import Engine

REPOSITORY = Path(__file__).resolve().parents[1]
PACK = REPOSITORY / "src" / "sayfirst_cli" / "packs" / "http-client"

#: Captured before any test wraps `urllib.request.urlopen`, so a test that
#: checks what the wrapper returns is checking against the real function and
#: not whatever `urlopen` happens to be bound to while it is installed.
REAL_URLOPEN = urllib.request.urlopen


# --- read_pack accepts the real pack ----------------------------------------


def test_the_shipped_pack_reads_as_one_point_governing_urlopen() -> None:
    pack = manifest.read_pack(PACK)
    assert pack.name == "http-client"
    assert len(pack.points) == 1
    point = pack.points[0]
    assert (point.module, point.attribute) == ("urllib.request", "urlopen")
    assert point.capability == "net.egress"
    assert point.digest == ("url",)


# --- a loopback server, so every granted-path test has somewhere to open ---


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def loopback_server() -> Iterator[str]:
    """A server on loopback answering `200`, and the URL that reaches it."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


# --- the wrapper, through the real engine, against a boundary double -------


@pytest.fixture
def engine() -> Iterator[Engine]:
    """One engine, always uninstalled, so no test leaves `urlopen` wrapped."""
    yield from engine_fixture()


@pytest.fixture
def governed(engine: Engine) -> FakeBoundary:
    """`urllib.request` is already imported at the top of this file, so the
    engine wraps `urlopen` in place — the same path a program that already did
    `import urllib.request` before `instrument run` reaches it would take."""
    return installed(engine, PACK)


def test_a_string_url_is_asked_and_the_status_is_recorded(governed: FakeBoundary) -> None:
    with loopback_server() as url:
        response = urllib.request.urlopen(url)
        status = response.status
        response.close()
    assert governed.asked == [("net.egress", {"url": url})]
    expected = hashlib.sha256(f"status:{status}".encode()).hexdigest()
    assert governed.handles[0].recorded == [expected]


def test_a_request_object_url_is_rendered_as_its_full_url(governed: FakeBoundary) -> None:
    with loopback_server() as url:
        request = urllib.request.Request(url)
        urllib.request.urlopen(request).close()
    assert governed.asked == [("net.egress", {"url": request.full_url})]
    assert governed.asked[0][1]["url"] == url


def test_the_wrapper_returns_the_real_response_so_the_with_form_still_works(
    governed: FakeBoundary,
) -> None:
    with loopback_server() as url, urllib.request.urlopen(url) as response:
        data = response.read()
    assert data == b"ok"
    assert isinstance(response, http.client.HTTPResponse)
    assert governed.handles[0].recorded


def test_a_result_with_no_real_status_records_no_outcome(
    governed: FakeBoundary, tmp_path: Path
) -> None:
    """`urlopen` also serves `file:` URLs — the same one function, no narrower
    seam — and a `file:` read returns `urllib.response.addinfourl`, which
    `hasattr(…, "status")` sees as `True` while `status` itself is `None`.
    Recording a digest for it would claim an outcome the response does not
    have; the wrapper must ask (the capability still applies — a `file:` read
    is governed under `net.egress` too, per the module docstring) and
    record nothing."""
    target = tmp_path / "local.txt"
    target.write_text("hello", encoding="utf-8")
    url = target.as_uri()
    response = urllib.request.urlopen(url)
    try:
        assert response.status is None
        response.read()
    finally:
        response.close()
    assert governed.asked == [("net.egress", {"url": url})]
    assert governed.handles[0].recorded == []


# --- a refused ask never reaches the real urlopen, for every call shape ----


#: Every call shape the one wrapped `urlopen` governs, spelled as a caller
#: spells it. A single URL is used for both — under refusal, `original` is
#: never called, so nothing here ever actually opens a connection.
REFUSAL_URL = "http://127.0.0.1:1/"
REQUESTS: dict[str, Callable[[], object]] = {
    "str": lambda: urllib.request.urlopen(REFUSAL_URL),
    "request": lambda: urllib.request.urlopen(urllib.request.Request(REFUSAL_URL)),
}

REFUSALS: dict[str, Callable[[], BaseException]] = {
    "denied": lambda: Denied(
        decision_ref="d-refused-1", capability="net.egress", reason="the plane said no"
    ),
    "suspended": lambda: Suspended(
        approval_ref="a-1", decision_ref="d-refused-2", capability="net.egress"
    ),
    "ask-refused": lambda: AskRefused(
        problem_code="ask-rejected", detail="the question was not accepted"
    ),
}


#: The shared stand-in harness, pointed at the one attribute this pack wraps.
governed_by = functools.partial(
    _governed_by,
    pack=PACK,
    holder=urllib.request,
    attribute="urlopen",
    original=REAL_URLOPEN,
)


@pytest.mark.parametrize("shape", sorted(REQUESTS))
@pytest.mark.parametrize("refusal", sorted(REFUSALS))
def test_a_refused_ask_never_reaches_the_real_urlopen(refusal: str, shape: str) -> None:
    """The one safety property this pack has: a refusal means no request."""
    boundary = RefusingBoundary(REFUSALS[refusal]())
    with (
        governed_by(boundary) as spy,
        pytest.raises(type(boundary.refusal)) as raised,
    ):
        REQUESTS[shape]()
    assert raised.value is boundary.refusal
    assert spy.calls == []
    assert boundary.asked == [("net.egress", {"url": REFUSAL_URL})]


@pytest.mark.parametrize("shape", sorted(REQUESTS))
def test_the_same_stand_in_records_the_call_when_the_ask_is_granted(shape: str) -> None:
    """Anti-vacuity for the refusals above: a boundary that grants, and a real
    request that really reaches a loopback server this time."""
    with loopback_server() as url:
        boundary = FakeBoundary()
        shapes: dict[str, Callable[[], object]] = {
            "str": lambda: urllib.request.urlopen(url),
            "request": lambda: urllib.request.urlopen(urllib.request.Request(url)),
        }
        with governed_by(boundary) as spy:
            shapes[shape]().close()
        assert len(spy.calls) == 1
        assert boundary.asked == [("net.egress", {"url": url})]


def test_the_stand_in_is_gone_and_the_real_function_is_back() -> None:
    with governed_by(FakeBoundary()) as spy:
        assert urllib.request.urlopen is not spy
        assert urllib.request.urlopen is not REAL_URLOPEN
    assert urllib.request.urlopen is REAL_URLOPEN


# --- through `sayfirst instrument run`, against a real daemon on the wire --


HTTP_PROGRAM = """\
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


server = HTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/").close()
finally:
    server.shutdown()
    server.server_close()
    thread.join()
"""


def test_a_governed_program_asks_net_egress_with_this_packs_capability(
    tmp_path: Path,
) -> None:
    """The pack this distribution actually ships, run through the real console
    script and the real engine, with only the daemon replaced."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "app.py").write_text(HTTP_PROGRAM, encoding="utf-8")
    with recording_daemon(tmp_path / "d.sock") as (socket_path, asks):
        finished = instrument(
            "run",
            "--pack",
            str(PACK),
            "--socket",
            str(socket_path),
            "--scope",
            "local",
            "--",
            "app.py",
            cwd=tree,
        )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert len(asks) == 1, asks
    assert asks[0]["capability"] == "net.egress"
