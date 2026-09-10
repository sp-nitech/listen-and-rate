"""Generate placeholder source/generated audio pairs for a local smoke test.

Real experiments point `stimuli_dirs` at actual recordings; this only exists so
`docker compose up` has something to serve before any data has been collected.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16000
DURATION = 1.5

# Distinct fundamentals so the two systems are audibly different, which makes a
# manual pass over the UI meaningful rather than a pair of identical tones.
_SYSTEM_F0 = {"source": 130.0, "generated": 190.0}


def _tone(f0: float, seed: int) -> np.ndarray:
    """A short vowel-ish tone: a few harmonics under a fade envelope."""
    t = np.linspace(0.0, DURATION, int(SAMPLE_RATE * DURATION), endpoint=False)
    rng = np.random.default_rng(seed)
    wave = sum(
        (1.0 / h) * np.sin(2 * np.pi * f0 * h * t + rng.uniform(0, 2 * np.pi))
        for h in (1, 2, 3, 4)
    )
    fade = np.minimum(1.0, np.minimum(t, DURATION - t) / 0.1)
    return (0.3 * wave / np.max(np.abs(wave)) * fade).astype(np.float32)


def main() -> None:
    """Write `--count` matching wav files into each system directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default="data/audio", type=Path)
    parser.add_argument("--count", default=6, type=int)
    args = parser.parse_args()

    for system, f0 in _SYSTEM_F0.items():
        directory = args.outdir / system
        directory.mkdir(parents=True, exist_ok=True)
        for i in range(1, args.count + 1):
            # Matching basenames across the two directories is what pairs a
            # source clip with its generated counterpart.
            path = directory / f"utt_{i:03d}.wav"
            sf.write(path, _tone(f0, seed=i), SAMPLE_RATE)
            print(f"wrote {path}")


if __name__ == "__main__":
    main()
