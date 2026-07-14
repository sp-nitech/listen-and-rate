"""ABX (discrimination) listening test configuration."""

from __future__ import annotations

from typing import Literal

from .two_system import TwoSystemComparisonConfig


class ABXConfig(TwoSystemComparisonConfig):
    """Top-level configuration for an ABX (discrimination) listening test."""

    test_type: Literal["abx"]
