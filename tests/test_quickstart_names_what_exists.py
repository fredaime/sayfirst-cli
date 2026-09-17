# SPDX-License-Identifier: Apache-2.0
"""Article 2 for the quickstart: every command it shows exists, with the flags it shows.

The page is a transcript of one run, so its commands and their flags are the claim a
reader acts on first. This guard reads every `$ … sayfirst …` line out of the page's
console blocks, asks the command's own parser whether that verb (and sub-verb) exists,
and checks every `--flag` on the line against that parser's help. A line the parser
would refuse is a page that would send the reader to an error.

It needs no daemon and no socket: `--help` is answered by the parser alone.
"""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path

import pytest

from sayfirst_cli.main import main

REPOSITORY = Path(__file__).resolve().parents[1]
QUICKSTART = REPOSITORY / "QUICKSTART.md"

#: The page shows at least this many command lines; fewer means the reader found
#: something other than the page this guard was written for.
COMMAND_LINE_FLOOR = 12

_COMMAND = re.compile(r"^\$ (?:\.venv/bin/)?sayfirst\s+(.*)$")
_FLAG = re.compile(r"(--[a-z][a-z-]*)")


def console_blocks(text: str) -> list[str]:
    """The fenced console blocks of the page, in order."""
    return re.findall(r"```console\n(.*?)```", text, flags=re.S)


def command_lines(text: str) -> list[str]:
    """Every `$ sayfirst …` line inside a console block, without the prompt."""
    lines: list[str] = []
    for block in console_blocks(text):
        for raw in block.splitlines():
            found = _COMMAND.match(raw)
            if found:
                lines.append(found.group(1))
    return lines


def verbs_of(command: str) -> list[str]:
    """The verb and, when present, the sub-verb before the first flag."""
    words: list[str] = []
    for word in command.split():
        if word.startswith("-"):
            break
        words.append(word)
    return words[:2]


_CHOICES = re.compile(r"\{([a-z,]+)\}")


def _help_of(words: list[str]) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            main([*words, "--help"])
        except SystemExit as stopped:
            if stopped.code not in (0, None):
                raise AssertionError(
                    f"the command refuses {' '.join(words)}: {out.getvalue()}"
                ) from None
    return out.getvalue()


def help_text(verbs: list[str]) -> str:
    """The parser's help for that verb chain; raises if any verb of it does not exist.

    The parser answers `--help` before it rejects a stray word, so a chain is checked
    one level at a time: each verb must be among the choices the level above lists in
    its usage line, and only then is its own help read.
    """
    text = _help_of([])
    for depth, verb in enumerate(verbs):
        listed = {choice for found in _CHOICES.findall(text) for choice in found.split(",")}
        assert verb in listed, f"{' '.join(verbs[:depth]) or 'sayfirst'} lists no {verb}: {listed}"
        text = _help_of(verbs[: depth + 1])
    return text


def test_the_page_exists_and_shows_enough_commands() -> None:
    lines = command_lines(QUICKSTART.read_text(encoding="utf-8"))
    assert len(lines) >= COMMAND_LINE_FLOOR, lines


@pytest.mark.parametrize("command", command_lines(QUICKSTART.read_text(encoding="utf-8")))
def test_every_command_the_page_shows_exists_with_its_flags(command: str) -> None:
    # A line with no verb (`sayfirst --help`) is checked against the top-level parser.
    verbs = verbs_of(command)
    text = help_text(verbs)
    for flag in _FLAG.findall(command.split("|")[0]):
        assert flag in text, f"{' '.join(verbs)} knows no {flag}: {command}"


def test_the_rule_fires_on_a_verb_the_command_lacks() -> None:
    with pytest.raises(AssertionError):
        help_text(["ask", "loudly"])


def test_the_rule_fires_on_a_flag_the_verb_lacks() -> None:
    text = help_text(["ask"])
    assert "--url" not in text, "the planted flag exists now; choose another"
