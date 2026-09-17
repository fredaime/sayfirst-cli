# SPDX-License-Identifier: Apache-2.0
"""A connection lost after it was verified is a non-answer, never a denial.

Articles 1 and 2 draw one line this client exists to hold: "could not ask" is
never written as "denied". The client already held it for a failure to *open*
the connection — the address that is not there, the process that is not the
daemon's principal. It did not hold it for a failure of the *request* on a
connection that opened and verified: `SocketClientProblem` raised from
`ask_decision` escaped `main`, so the process ended in a traceback with exit
code 1 and no envelope — and 1 is the code this client publishes for `deny`.

Automation reading that code stops the effect, which is right, and records a
refusal that nobody gave, which is the false fact article 2 forbids.

The socket here is real and nothing is patched: the far end accepts, is
verified, and hangs up before the status line, which is what a daemon restarted
between the accept and the answer does.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from canned_daemon import hanging_up_after_accept

from sayfirst_cli import exit_codes
from sayfirst_cli.ask import main


def run(*argv: str) -> tuple[int, str, str]:
    """Run the command and return exactly what a shell would see."""
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def test_a_connection_lost_after_the_question_exits_could_not_ask(tmp_path: Path) -> None:
    """Articles 1 and 2: the code is 4, and it is emphatically not 1."""
    with hanging_up_after_accept(tmp_path / "lost.sock") as socket_path:
        exit_code, stdout, stderr = run(
            "--capability", "example.effect", "--scope", "local", "--socket", str(socket_path)
        )

    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK, (exit_code, stdout, stderr)
    assert exit_code != exit_codes.EXIT_DENY
    assert stdout == ""


def test_the_lost_connection_is_rendered_as_an_envelope_and_not_a_traceback(
    tmp_path: Path,
) -> None:
    """Article 2: the caller is told what happened, in the shape every answer has."""
    with hanging_up_after_accept(tmp_path / "lost.sock") as socket_path:
        exit_code, _, stderr = run(
            "--capability",
            "example.effect",
            "--scope",
            "local",
            "--socket",
            str(socket_path),
            "--json",
        )

    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK, stderr
    document = json.loads(stderr)
    assert document["problem"]["code"] == "unreachable", document
    assert "result" not in document, document
    # The far end *was* verified before the question was written; saying it was
    # not would be a second false fact about the same event.
    assert document["verification"]["verified"] is True, document


def test_the_prose_rendering_says_could_not_ask(tmp_path: Path) -> None:
    """Article 1: the words a person reads distinguish it from a denial too."""
    with hanging_up_after_accept(tmp_path / "lost.sock") as socket_path:
        exit_code, _, stderr = run(
            "--capability", "example.effect", "--scope", "local", "--socket", str(socket_path)
        )

    assert exit_code == exit_codes.EXIT_COULD_NOT_ASK, stderr
    assert "could not ask" in stderr
    assert "denied" not in stderr
