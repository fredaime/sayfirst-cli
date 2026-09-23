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
starts itself, on loopback, so nothing here reaches the network. The redirect
tests at the end do not even do that: a redirect needs an answer and not a
connection, so they supply the `302` and the `200` from a handler of their own,
in memory, and no socket is opened at all.

The doubles all three of these suites drive their packs against — `FakeBoundary`,
`RefusingBoundary`, `Spy` and the engine harness — are in `tests/pack_doubles.py`,
which records what three copies of them cost. What stays here is this pack's own:
its path, the call shapes it governs, and the capability its refusals name.
"""

from __future__ import annotations

import functools
import hashlib
import http.client
import io
import threading
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from email.message import Message
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.response import addinfourl

import pytest
from canned_daemon import answering_by_path
from documents import no_evidence_page, recorded_effect_page
from governed_programs import instrument, recording_daemon
from pack_doubles import FakeBoundary, Handle, RefusingBoundary, engine_fixture, installed
from pack_doubles import governed_by as _governed_by
from sayfirst_boundary import AskRefused, Denied, Suspended
from sayfirst_boundary.digest import arguments_digest

from sayfirst_cli import exit_codes
from sayfirst_cli.instrument import manifest
from sayfirst_cli.instrument.engine import Engine

REPOSITORY = Path(__file__).resolve().parents[1]
PACK = REPOSITORY / "src" / "sayfirst_cli" / "packs" / "http-client"

#: Captured before any test wraps `urllib.request.urlopen`, so a test that
#: checks what the wrapper returns is checking against the real function and
#: not whatever `urlopen` happens to be bound to while it is installed.
REAL_URLOPEN = urllib.request.urlopen

#: The opener's own `open`, captured for the same reason: the pack governs it
#: for the length of a governed call, and « it was put back » has to be checked
#: against the object that was there before any of this ran.
REAL_OPEN = urllib.request.OpenerDirector.open


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


# --- a redirect makes a second request, and it is asked about too ---------


#: The two addresses of one ordinary redirect. `.invalid` is reserved by
#: RFC 2606 and resolves nowhere, which is a second guard beside the handler
#: below: nothing here can reach a network even if the handler were bypassed.
FIRST = "http://redirect.invalid/first"
SECOND = "http://redirect.invalid/second"


class InMemoryRedirect(urllib.request.HTTPHandler):
    """A `302` at `/first` and a `200` at `/second`, answered without a socket.

    `urllib`'s own redirect machinery runs in full over these two answers —
    `HTTPErrorProcessor` sees the `302`, hands it to `HTTPRedirectHandler`, and
    that handler makes the second request through its opener. That second
    request is the effect this section is about, and it is real: the
    interpreter reports a second `urllib.Request` for it, which is the event
    the verifier watches.
    """

    def http_open(self, request: urllib.request.Request) -> addinfourl:
        headers = Message()
        code = 200
        if request.full_url == FIRST:
            headers["Location"] = SECOND
            code = 302
        answer = addinfourl(io.BytesIO(b""), headers, request.full_url, code)
        answer.msg = "in memory"
        return answer


@contextmanager
def redirecting_opener() -> Iterator[None]:
    """Install the in-memory opener, and put back whatever was there before.

    Installed BEFORE the engine, deliberately: that is the order the
    reproduction of this defect used, and the order a program that built its
    opener during its own imports produces. A fix that only governed openers
    built after installation would pass with the two lines the other way round
    and leave the reported defect in place.
    """
    previous = urllib.request._opener
    urllib.request.install_opener(urllib.request.build_opener(InMemoryRedirect()))
    try:
        yield
    finally:
        urllib.request._opener = previous


def test_the_second_request_a_redirect_makes_is_asked_about_too(engine: Engine) -> None:
    """One `urlopen`, two requests, two asks — in the order they were made.

    `urlopen` is wrapped once, but a redirect is not a second call to it: the
    redirect handler goes back through its opener. So a pack that asked only
    where `urlopen` was called asked about the first address and let the second
    request leave the process with no question put about it at all.
    """
    with redirecting_opener():
        boundary = installed(engine, PACK)
        urllib.request.urlopen(FIRST).close()
    assert boundary.asked == [
        ("net.egress", {"url": FIRST}),
        ("net.egress", {"url": SECOND}),
    ]


def test_a_refused_redirect_never_makes_the_second_request(engine: Engine) -> None:
    """Anti-vacuity for the ask above: the second ask is a real gate, not a note.

    The boundary grants the first request and refuses the second, and the
    second address is never opened — read off the handler's own record of what
    it was asked for, so « it did not happen » is measured rather than inferred.
    """
    opened: list[str] = []

    class Recording(InMemoryRedirect):
        def http_open(self, request: urllib.request.Request) -> addinfourl:
            opened.append(request.full_url)
            return super().http_open(request)

    class GrantsThenRefuses:
        """`FakeBoundary`'s shape, with the second answer a refusal.

        Not one of the shared doubles: neither of them refuses only after
        granting, and that is exactly the sequence a governed redirect needs.
        """

        def __init__(self) -> None:
            self.asked: list[tuple[str, dict[str, object]]] = []
            self.refusal = Denied(
                decision_ref="d-redirect", capability="net.egress", reason="the plane said no"
            )

        @contextmanager
        def request(
            self, capability: str, arguments: dict[str, object], *, scope: str = "local"
        ) -> Iterator[Handle]:
            self.asked.append((capability, dict(arguments)))
            if len(self.asked) > 1:
                raise self.refusal
            yield Handle()

    boundary = GrantsThenRefuses()
    with redirecting_opener():
        previous = urllib.request._opener
        urllib.request.install_opener(urllib.request.build_opener(Recording()))
        try:
            engine.install([manifest.read_pack(PACK)], boundary, scope="local")
            with pytest.raises(Denied) as raised:
                urllib.request.urlopen(FIRST)
        finally:
            urllib.request._opener = previous
    assert raised.value is boundary.refusal
    assert [address for _, address in ((c, a["url"]) for c, a in boundary.asked)] == [FIRST, SECOND]
    assert opened == [FIRST], "the refused redirect opened the second address anyway"


#: The same redirect as a program, for the runs that go through a real process.
REDIRECT_PROGRAM = f"""\
import io
import urllib.request
from email.message import Message
from urllib.response import addinfourl

FIRST = {FIRST!r}
SECOND = {SECOND!r}


class InMemory(urllib.request.HTTPHandler):
    def http_open(self, request):
        headers = Message()
        code = 200
        if request.full_url == FIRST:
            headers["Location"] = SECOND
            code = 302
        answer = addinfourl(io.BytesIO(b""), headers, request.full_url, code)
        answer.msg = "in memory"
        return answer


urllib.request.install_opener(urllib.request.build_opener(InMemory()))
urllib.request.urlopen(FIRST).close()
print("followed the redirect")
"""


def a_redirecting_tree(root: Path) -> Path:
    tree = root / "redirect"
    tree.mkdir()
    (tree / "app.py").write_text(REDIRECT_PROGRAM, encoding="utf-8")
    return tree


def test_a_governed_redirect_puts_both_addresses_on_the_wire(tmp_path: Path) -> None:
    """The shipped pack, the real console script, a real daemon reading the wire."""
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
            cwd=a_redirecting_tree(tmp_path),
        )
    assert finished.returncode == 0, (finished.stdout, finished.stderr)
    assert [ask["capability"] for ask in asks] == ["net.egress", "net.egress"], asks
    # What crosses the wire is the digest and never the address (article 11),
    # so which ADDRESS each ask was about is read by digesting the two the
    # program used with the boundary's own recipe.
    assert [ask["arguments_digest"] for ask in asks] == [
        arguments_digest({"url": FIRST}),
        arguments_digest({"url": SECOND}),
    ], asks


def test_the_verifier_needs_a_decision_for_each_of_the_redirects_two_requests(
    tmp_path: Path,
) -> None:
    """What the shipped verifier asks of an ordinary redirect: two records.

    The pair this test and the one above form is the whole of finding F11. The
    verifier counts the interpreter's own `urllib.Request` events and consults
    the chain once for each, so a one-hop redirect is `governed` only against
    two recorded decisions and is a finding against one. The pack above now
    produces exactly those two, so the two shipped halves agree about a
    redirect instead of contradicting each other.
    """
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page("net.egress", count=2)])}
    with answering_by_path(tmp_path / "two.sock", routes) as address:
        code, stdout, stderr = _verify(address, a_redirecting_tree(tmp_path))
    assert code == 0, (stdout, stderr)
    assert "governed http-client urllib.request.urlopen net.egress events=2" in stdout
    assert "followed the redirect" in stderr

    one = tmp_path / "one"
    one.mkdir()
    routes = {"/scopes/": (200, [no_evidence_page(), recorded_effect_page("net.egress", count=1)])}
    with answering_by_path(one / "one.sock", routes) as address:
        code, stdout, stderr = _verify(address, a_redirecting_tree(one))
    assert code == exit_codes.EXIT_CHECK_FAILED, (stdout, stderr)
    assert "ungoverned http-client urllib.request.urlopen net.egress events=1" in stdout


def _verify(address: Path, tree: Path) -> tuple[int, str, str]:
    """`sayfirst instrument verify --ungoverned`, the way a person runs it."""
    finished = instrument(
        "verify",
        "--pack",
        str(PACK),
        "--socket",
        str(address),
        "--scope",
        "local",
        "--ungoverned",
        "--",
        "app.py",
        cwd=tree,
    )
    return finished.returncode, finished.stdout, finished.stderr


def test_the_opener_is_governed_only_while_a_call_is_in_flight(engine: Engine) -> None:
    """The reach of the fix, both ends of it: in place during, put back after.

    Read from inside the handler, which the opener calls while it is running,
    so « governed during the call » is observed rather than assumed — and read
    again afterwards against the object captured before any test ran, so
    « put back » is the very object and not one that resembles it.
    """
    during: list[object] = []

    class Observing(InMemoryRedirect):
        def http_open(self, request: urllib.request.Request) -> addinfourl:
            during.append(urllib.request.OpenerDirector.open)
            return super().http_open(request)

    previous = urllib.request._opener
    urllib.request.install_opener(urllib.request.build_opener(Observing()))
    try:
        installed(engine, PACK)
        assert urllib.request.OpenerDirector.open is REAL_OPEN, "governed before any call"
        urllib.request.urlopen(FIRST).close()
    finally:
        urllib.request._opener = previous
    assert len(during) == 2, during
    assert REAL_OPEN not in during, "the redirect was followed through the ungoverned open"
    assert urllib.request.OpenerDirector.open is REAL_OPEN, "the opener was left governed"
