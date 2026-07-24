"""Regenerate the README interface screenshots.

For each (config, theme) pair below, launch the FastAPI dev server, drive a
headless Chromium (Playwright) to the rendered test interface with the colour
theme forced via localStorage, and write a PNG to assets/. AB is shot in light
and MOS in dark so the README advertises both the test-type variety and the
theme toggle (its sun/moon icon sits in the top-right of every shot).

Run with `make screenshots` (needs the dev dependency group and a one-off
`playwright install chromium`).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS = REPO_ROOT / "assets"
HOST = "127.0.0.1"
PORT = 8000

# (config, theme, output filename). config.mos.yaml / config.ab.yaml already
# point at the bundled stimuli/examples audio, so they render as-is.
SHOTS = [
    ("examples/config.ab.yaml", "light", "ab-interface.png"),
    ("examples/config.mos.yaml", "dark", "mos-interface.png"),
]


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> None:
    """Block until something accepts connections on host:port (or time out)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"server did not open {host}:{port} within {timeout:.0f}s")


def _serve(config: str) -> subprocess.Popen:
    """Start the FastAPI dev server for `config`, returning once it is ready."""
    env = {**os.environ, "LISTEN_AND_RATE_CONFIG": config}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "listen_and_rate.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    try:
        _wait_for_port(HOST, PORT)
    except BaseException:
        proc.terminate()
        raise
    return proc


def _capture(browser, theme: str, output: str) -> None:
    """Load the rendered interface with `theme` forced and screenshot it."""
    context = browser.new_context(
        viewport={"width": 1000, "height": 700},
        device_scale_factor=2,
    )
    # Runs before the page's own scripts on navigation, so theme.js reads this
    # value on load (it defaults to dark when the key is absent).
    context.add_init_script(f"localStorage.setItem('theme', {theme!r})")
    page = context.new_page()
    page.goto(f"http://{HOST}:{PORT}/", wait_until="networkidle")
    # Both MOS and the paired-choice tests render into .stimulus-page.
    page.wait_for_selector(".stimulus-page", timeout=15000)
    page.wait_for_timeout(500)  # let the audio time bar settle
    page.screenshot(path=str(ASSETS / output))
    context.close()


def main() -> None:
    """Regenerate every screenshot in SHOTS."""
    ASSETS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for config, theme, output in SHOTS:
                proc = _serve(config)
                try:
                    _capture(browser, theme, output)
                    print(f"wrote assets/{output} ({theme}, {config})")
                finally:
                    proc.terminate()
                    proc.wait(timeout=10)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
