"""Tests for the pre-test checks every entry point runs."""

from __future__ import annotations

from listen_and_rate import checks


def test_every_check_runs_in_its_order(monkeypatch):
    # Order matters twice over. Duration goes first because its lengths are
    # already read and it does not depend on playback level, so the cheapest
    # and coarsest check fails fast. Silence goes after loudness because its
    # floor is absolute, so silence figures taken from clips whose levels
    # disagree may say more about the level difference.
    ran = []
    for name in ("duration", "loudness", "silence"):
        monkeypatch.setattr(
            checks,
            f"run_configured_{name}_check",
            lambda config, name=name: ran.append((name, config)),
        )
    checks.run_configured_checks("config")
    assert ran == [
        ("duration", "config"),
        ("loudness", "config"),
        ("silence", "config"),
    ]


def test_the_server_runs_them_at_startup(config_yaml, monkeypatch):
    # The export runs them too (see tests/cli/test_export_php_deploy.py), so
    # an experiment cannot pass QA on one backend and fail it on the other.
    from fastapi.testclient import TestClient

    from listen_and_rate import main

    checked: list[str] = []
    monkeypatch.setattr(
        main, "run_configured_checks", lambda c: checked.append(c.experiment_id)
    )
    monkeypatch.setenv("LISTEN_AND_RATE_CONFIG", str(config_yaml))
    with TestClient(main.create_app()):
        pass
    assert checked == ["config"]
