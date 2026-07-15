"""Test helpers shared across more than one test subpackage.

Per-subpackage helpers live in each package's own `_helpers.py`; this holds
the few that several packages need (imported as `from .._helpers import ...`).
"""

from __future__ import annotations

from pathlib import Path


def write_sine(path, seconds=1.5, amplitude=0.3, rate=16000, freq=440.0):
    """Write a mono sine WAV to `path` (a real, non-silent clip for loudness tests).

    soundfile/numpy are imported lazily so importing this module stays cheap and
    dependency-free; callers that need audio already guard with importorskip.
    """
    import numpy as np
    import soundfile as sf

    t = np.arange(int(seconds * rate)) / rate
    sf.write(
        str(path), (amplitude * np.sin(2 * np.pi * freq * t)).astype("float32"), rate
    )
    return Path(path)
