"""The pre-test audio checks, run in one order by every entry point.

Both the FastAPI server and the PHP export run them before serving a config,
so a check added here reaches both.
"""

from __future__ import annotations

from .config import Config
from .duration import run_configured_duration_check
from .loudness import run_configured_loudness_check
from .silence import run_configured_silence_check


def run_configured_checks(config: Config) -> None:
    """Run every check `config` configures, in an order that matters.

    Duration goes first: it reads the lengths load_config already has, opens
    no file and does not depend on playback level, so the cheapest and
    coarsest check fails fast. Silence goes after loudness because its floor
    is absolute, so silence figures taken from clips whose levels disagree may
    say more about the level difference. Each prints what it finds and raises
    SystemExit when its threshold is exceeded.
    """
    run_configured_duration_check(config)
    run_configured_loudness_check(config)
    run_configured_silence_check(config)
