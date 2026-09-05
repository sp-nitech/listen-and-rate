"""Test helpers shared across more than one test subpackage.

Per-subpackage helpers live in each package's own `_helpers.py`; this holds
the few that several packages need (imported as `from .._helpers import ...`).
"""

from __future__ import annotations

from pathlib import Path

import yaml


def write_config(tmp_path: Path, data: dict, name: str = "config.yaml") -> Path:
    """Dump a config dict to `tmp_path/name` (UTF-8) and return the path.

    Shared by the config/cli/router tests and, via name="report.yaml", the
    report-config tests. allow_unicode keeps non-ASCII fields (e.g. Japanese
    titles) as raw UTF-8 rather than escape sequences; the explicit encoding
    keeps the write working on platforms whose default is not UTF-8 (Windows).
    """
    p = tmp_path / name
    p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return p


def write_sine(path, seconds=1.5, amplitude=0.3, rate=16000, freq=440.0):
    """Write a mono sine WAV to `path` (a real, non-silent clip for loudness tests).

    soundfile/numpy are imported lazily so importing this module stays cheap
    for the callers that only want write_config.
    """
    import numpy as np
    import soundfile as sf

    t = np.arange(int(seconds * rate)) / rate
    sf.write(
        str(path), (amplitude * np.sin(2 * np.pi * freq * t)).astype("float32"), rate
    )
    return Path(path)
