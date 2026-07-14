"""Configuration loader and Pydantic models for the audio evaluation tool.

Split into one submodule per test type (mos.py, dmos.py, cmos.py, ab.py,
abx.py, mushra.py) plus shared building blocks (base.py, two_system.py,
_utils.py) and the YAML loader (loader.py). This file re-exports the public
API so existing `from listen_and_rate.config import ...` call sites are
unaffected by the split.
"""

from __future__ import annotations

from .ab import ABConfig, ABTrial, build_ab_trials
from .abx import ABXConfig
from .base import (
    BaseTestConfig,
    KeyboardShortcuts,
    MetadataFieldConfig,
    OutputConfig,
    StimuliConfig,
    StimuliDirsConfig,
    StimulusConfig,
    SystemDirEntry,
)
from .cmos import CMOSConfig
from .dmos import DMOSConfig, DMOSTrial, build_dmos_trials
from .errors import format_config_error
from .loader import Config, load_config, load_config_or_exit
from .mos import MOSConfig
from .mushra import MUSHRAConfig, MUSHRATrial, build_mushra_trials
from .report import FontConfig, ReportConfig, ScaleConfig, load_report_config_or_exit
from .two_system import TwoSystemComparisonConfig
from .xab import XABConfig, XABTrial, build_xab_trials

__all__ = [
    "ABConfig",
    "ABTrial",
    "ABXConfig",
    "BaseTestConfig",
    "CMOSConfig",
    "Config",
    "DMOSConfig",
    "DMOSTrial",
    "FontConfig",
    "KeyboardShortcuts",
    "MOSConfig",
    "MUSHRAConfig",
    "MUSHRATrial",
    "MetadataFieldConfig",
    "OutputConfig",
    "ReportConfig",
    "ScaleConfig",
    "StimuliConfig",
    "StimuliDirsConfig",
    "StimulusConfig",
    "SystemDirEntry",
    "TwoSystemComparisonConfig",
    "XABConfig",
    "XABTrial",
    "build_ab_trials",
    "build_dmos_trials",
    "build_mushra_trials",
    "build_xab_trials",
    "format_config_error",
    "load_config",
    "load_config_or_exit",
    "load_report_config_or_exit",
]
