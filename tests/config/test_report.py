"""Tests for the report config: ReportConfig defaults, validation, loading."""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from listen_and_rate.config import ReportConfig, load_report_config_or_exit


def _write(tmp_path, data: dict):
    p = tmp_path / "report.yaml"
    p.write_text(yaml.dump(data, allow_unicode=True))
    return p


def test_defaults_when_empty():
    rc = ReportConfig()
    assert rc.scale.width == 1.0
    assert rc.scale.height == 1.0
    assert rc.confidence == 0.95
    assert rc.font.family == "sans-serif"
    assert rc.font.size == 13
    assert rc.order is None
    assert rc.labels is None


def test_parses_all_fields():
    rc = ReportConfig(
        scale={"width": 1.5, "height": 2.0},
        confidence=0.99,
        font={"family": "Georgia", "size": 20},
        order=["A", "B"],
        labels={"A": "Proposed", "B": "Baseline"},
    )
    assert rc.scale.width == 1.5
    assert rc.scale.height == 2.0
    assert rc.confidence == 0.99
    assert rc.font.family == "Georgia"
    assert rc.font.size == 20
    assert rc.order == ["A", "B"]
    assert rc.labels == {"A": "Proposed", "B": "Baseline"}


def test_confidence_must_be_between_zero_and_one():
    with pytest.raises(ValidationError):
        ReportConfig(confidence=1.0)
    with pytest.raises(ValidationError):
        ReportConfig(confidence=0.0)


def test_scale_must_be_positive():
    with pytest.raises(ValidationError):
        ReportConfig(scale={"width": 0})
    with pytest.raises(ValidationError):
        ReportConfig(scale={"height": -1})


def test_font_size_must_be_positive():
    with pytest.raises(ValidationError):
        ReportConfig(font={"size": 0})


def test_unknown_top_level_field_rejected():
    with pytest.raises(ValidationError):
        ReportConfig(width=900)  # old-style flat field is no longer accepted


def test_unknown_scale_field_rejected():
    with pytest.raises(ValidationError):
        ReportConfig(scale={"depth": 1.0})


def test_groups_default_to_none():
    assert ReportConfig().groups is None


def test_groups_parse_label_and_filters():
    rc = ReportConfig(
        groups=[
            {"label": "All"},
            {
                "label": "Speaker F01 on headphones",
                "metadata_filter": {"device": "Headphones"},
                "stimuli_filter": {"utterance": ["F01_*", "F02_*"]},
            },
        ]
    )
    assert rc.groups is not None
    assert rc.groups[0].label == "All"
    assert rc.groups[0].metadata_filter is None
    assert rc.groups[0].stimuli_filter is None
    assert rc.groups[1].metadata_filter == {"device": "Headphones"}
    assert rc.groups[1].stimuli_filter == {"utterance": ["F01_*", "F02_*"]}


def test_groups_coerce_numeric_filter_values_to_str():
    # An unquoted numeric YAML value (e.g. `age: 30`) must match the stored
    # string form, like the shortcut key coercions elsewhere in the config.
    rc = ReportConfig(groups=[{"label": "g", "metadata_filter": {"age": 30}}])
    assert rc.groups is not None
    assert rc.groups[0].metadata_filter == {"age": "30"}


def test_groups_duplicate_labels_rejected():
    with pytest.raises(ValidationError):
        ReportConfig(groups=[{"label": "same"}, {"label": "same"}])


def test_groups_stimuli_filter_rejects_non_stimulus_key():
    # stimuli_filter keys are a fixed allowlist (utterance/system); an outcome
    # column like 'rating' must be rejected at load time.
    with pytest.raises(ValidationError):
        ReportConfig(groups=[{"label": "g", "stimuli_filter": {"rating": "5"}}])


def test_groups_unknown_field_rejected():
    with pytest.raises(ValidationError):
        ReportConfig(groups=[{"label": "g", "bogus": 1}])


def test_groups_label_required():
    with pytest.raises(ValidationError):
        ReportConfig(groups=[{"metadata_filter": {"device": "Headphones"}}])


def test_load_report_config_or_exit_reads_yaml(tmp_path):
    path = _write(tmp_path, {"confidence": 0.9, "labels": {"A": "Proposed"}})
    rc = load_report_config_or_exit(path)
    assert rc.confidence == 0.9
    assert rc.labels == {"A": "Proposed"}


def test_load_report_config_or_exit_empty_file_uses_defaults(tmp_path):
    path = tmp_path / "report.yaml"
    path.write_text("")
    rc = load_report_config_or_exit(path)
    assert rc == ReportConfig()


def test_load_report_config_or_exit_exits_cleanly_on_bad_value(tmp_path):
    path = _write(tmp_path, {"confidence": 2})
    with pytest.raises(SystemExit) as excinfo:
        load_report_config_or_exit(path)
    # Clean, URL-free message (see format_config_error).
    assert "errors.pydantic.dev" not in str(excinfo.value)


def test_load_report_config_or_exit_exits_on_unknown_field(tmp_path):
    path = _write(tmp_path, {"nonsense": True})
    with pytest.raises(SystemExit):
        load_report_config_or_exit(path)
