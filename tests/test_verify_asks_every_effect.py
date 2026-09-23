# SPDX-License-Identifier: Apache-2.0
"""A verifying run asks the control plane for every effect it sees.

`run` holds what it is granted: an identical later effect is answered by the
grant an earlier allow minted, with nothing asked and so nothing recorded
(article 10). The verifier's proof is one recorded decision for each effect it
saw, so under that cache an effect repeated within a grant's lifetime read as
ungoverned — stopped, and reported with status 6. The end-to-end case lives with
the control plane, whose daemon mints grants
(`test_a_verification_of_one_effect_repeated_is_clean`); this holds, here, that
the verifier hands the program over asking for every effect.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from contract_absence import contract_is_installed, skip_without_the_contract


def test_the_verifier_hands_the_program_over_asking_for_every_effect(
    request, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not contract_is_installed():
        skip_without_the_contract(request, "the harness builds the contract's own profile")
    from sayfirst_contract.transport.socket_client import SocketProfile

    from sayfirst_cli.instrument import harness, launch

    handed: dict[str, object] = {}

    def run(packs, profile, target, **options) -> int:  # type: ignore[no-untyped-def]
        handed.update(options)
        return 0

    monkeypatch.setattr(launch, "run", run)
    configured = harness.Configuration(
        packs=(),
        profile=SocketProfile(str(tmp_path / "daemon.sock")),
        principal=None,
        governed=True,
        report=tmp_path / "report.json",
        outcome=tmp_path / "outcome.json",
    )

    class Watch:
        def arm(self, *_: object) -> None: ...

    assert harness._run_the_target(configured, [], ["program.py"], Watch(), "run-token") == 0
    assert handed["hold_grants"] is False
    assert handed["correlation"] == "run-token"


def test_a_governed_run_keeps_the_grants_article_10_gives_it(
    request, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the proof asks for every effect; `run` answers a repeat from its grant."""
    if not contract_is_installed():
        skip_without_the_contract(request, "the launcher builds the boundary")
    from sayfirst_contract.transport.socket_client import SocketProfile

    from sayfirst_cli.instrument import launch

    built: dict[str, object] = {}

    class Boundary:
        def __init__(self, **options: object) -> None:
            built.update(options)

    monkeypatch.setattr(launch, "Boundary", Boundary)
    monkeypatch.setattr(
        launch, "Engine", lambda: type("E", (), {"install": lambda *a, **k: None})()
    )
    monkeypatch.setattr(launch, "_hand_off", lambda program, err, starting: 0)
    program = tmp_path / "program.py"
    program.write_text("pass\n", encoding="utf-8")
    code = launch.run(
        [], SocketProfile(str(tmp_path / "daemon.sock")), [str(program)], out=None, err=None
    )  # type: ignore[arg-type]
    assert code == 0
    assert built["hold_grants"] is True
