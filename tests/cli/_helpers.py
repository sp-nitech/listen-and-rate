"""Shared config-writing helper for the CLI tests."""

from __future__ import annotations

from pathlib import Path

import yaml


def _write_config_yaml(tmp_path: Path, config: dict) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(config))
    return p
