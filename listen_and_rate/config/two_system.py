"""Shared base for 2-system stimuli_dirs test types (AB, ABX, CMOS)."""

from __future__ import annotations

from pydantic import model_validator
from pydantic_core import PydanticCustomError

from .base import BaseTestConfig


class TwoSystemComparisonConfig(BaseTestConfig):
    """Shared base for 2-system stimuli_dirs test types (AB, ABX, ...)."""

    @model_validator(mode="after")
    def check_requires_two_system_dirs(self) -> TwoSystemComparisonConfig:
        """Require exactly 2 stimuli_dirs.systems entries and no explicit stimuli."""
        if self.stimuli is not None:
            raise PydanticCustomError(
                "two_system_requires_stimuli_dirs",
                "this test type requires 'stimuli_dirs' (explicit 'stimuli' lists "
                "are not supported)",
            )
        n = len(self.stimuli_dirs.systems) if self.stimuli_dirs else 0
        if n != 2:
            raise PydanticCustomError(
                "two_system_count",
                "this test type requires exactly 2 stimuli_dirs.systems "
                "entries, got {count}",
                {"count": n},
            )
        return self
