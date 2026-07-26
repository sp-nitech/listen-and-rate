from __future__ import annotations

import csv
import json

import pytest

from listen_and_rate.storage import (
    CSVResultSaver,
    JSONResultSaver,
    ResultExistsError,
    ResultSaver,
    make_result_saver,
)

SESSION_ID = "test-session-001"
TEST_TYPE = "mos"
EXPERIMENT_ID = "exp"
RATINGS = [
    {"system": "sys_a", "item": "utt001", "rating": 4},
    {"system": "sys_b", "item": "utt002", "rating": 3},
]
METADATA = {"listener": "Alice", "device": "Headphones"}


# -- CSVResultSaver ---------------------------------------------------------


def test_csv_saver_writes_correct_header(tmp_path):
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert set(rows[0].keys()) == {
        "session_id",
        "timestamp",
        "test_type",
        "system",
        "item",
        "rating",
    }


def test_csv_saver_writes_correct_values(tmp_path):
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert len(rows) == 2
    assert rows[0]["session_id"] == SESSION_ID
    assert rows[0]["test_type"] == TEST_TYPE
    assert rows[0]["system"] == "sys_a"
    assert rows[0]["item"] == "utt001"
    assert rows[0]["rating"] == "4"


def test_csv_saver_with_metadata_inserts_prefixed_columns(tmp_path):
    # Form answers are namespaced with a metadata_/survey_ column prefix, so
    # they can never collide with the saver-written result columns and stay
    # distinguishable from each other in the flat CSV.
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID, metadata_keys=list(METADATA.keys()))
    saver.save(SESSION_ID, TEST_TYPE, RATINGS, metadata=METADATA)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert rows[0]["metadata_listener"] == "Alice"
    assert rows[0]["metadata_device"] == "Headphones"
    keys = list(rows[0].keys())
    assert keys.index("metadata_listener") > keys.index("test_type")
    assert keys.index("system") > keys.index("metadata_device")


def test_csv_saver_metadata_key_named_like_result_column_cannot_collide(tmp_path):
    # The prefix namespace is what allows a metadata field literally named
    # 'system': it lands in metadata_system, never touching the stimulus one.
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID, metadata_keys=["system"])
    saver.save(SESSION_ID, TEST_TYPE, RATINGS, metadata={"system": "windows"})
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert rows[0]["metadata_system"] == "windows"
    assert rows[0]["system"] == "sys_a"


def test_csv_saver_with_survey_appends_prefixed_columns_after_metadata(tmp_path):
    saver = CSVResultSaver(
        tmp_path,
        EXPERIMENT_ID,
        metadata_keys=list(METADATA.keys()),
        survey_keys=["trial_count"],
    )
    saver.save(
        SESSION_ID,
        TEST_TYPE,
        RATINGS,
        metadata=METADATA,
        survey={"trial_count": "adequate"},
    )
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert rows[0]["survey_trial_count"] == "adequate"
    keys = list(rows[0].keys())
    assert keys.index("survey_trial_count") > keys.index("metadata_device")
    assert keys.index("system") > keys.index("survey_trial_count")


def test_csv_saver_each_session_is_separate_file(tmp_path):
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID)
    saver.save("session-1", TEST_TYPE, RATINGS)
    saver.save("session-2", TEST_TYPE, RATINGS)
    assert (tmp_path / EXPERIMENT_ID / "session-1.csv").exists()
    assert (tmp_path / EXPERIMENT_ID / "session-2.csv").exists()


def test_csv_saver_each_session_has_own_header(tmp_path):
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID)
    saver.save("session-1", TEST_TYPE, RATINGS)
    saver.save("session-2", TEST_TYPE, RATINGS)
    assert (tmp_path / EXPERIMENT_ID / "session-1.csv").read_text(
        encoding="utf-8"
    ).count("session_id") == 1
    assert (tmp_path / EXPERIMENT_ID / "session-2.csv").read_text(
        encoding="utf-8"
    ).count("session_id") == 1


def test_csv_saver_creates_output_directory(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    CSVResultSaver(nested, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    assert (nested / EXPERIMENT_ID / f"{SESSION_ID}.csv").exists()


def test_csv_saver_infers_columns_from_ab_row_shape(tmp_path):
    ab_rows = [
        {"system_a": "A", "system_b": "B", "item": "u1", "winner": "a"},
        {"system_a": "A", "system_b": "B", "item": "u2", "winner": "="},
    ]
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, "ab", ab_rows)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert list(rows[0].keys()) == [
        "session_id",
        "timestamp",
        "test_type",
        "system_a",
        "system_b",
        "item",
        "winner",
    ]
    assert rows[0]["winner"] == "a"
    assert rows[1]["winner"] == "="


def test_csv_saver_infers_columns_from_abx_row_shape(tmp_path):
    abx_rows = [
        {"system_a": "A", "system_b": "B", "item": "u1", "correct": True},
        {"system_a": "A", "system_b": "B", "item": "u2", "correct": False},
    ]
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, "abx", abx_rows)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert list(rows[0].keys()) == [
        "session_id",
        "timestamp",
        "test_type",
        "system_a",
        "system_b",
        "item",
        "correct",
    ]
    # Booleans are written as JSON-style lowercase tokens (matching the JSON
    # saver's native true/false), not Python's str(bool) "True"/"False".
    assert rows[0]["correct"] == "true"
    assert rows[1]["correct"] == "false"


def test_csv_saver_refuses_to_overwrite_existing_session(tmp_path):
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID)
    saver.save(SESSION_ID, TEST_TYPE, RATINGS)
    original = (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").read_text(
        encoding="utf-8"
    )
    with pytest.raises(ResultExistsError):
        saver.save(SESSION_ID, TEST_TYPE, [{"system": "x", "item": "y", "rating": 1}])
    # The collected data must be left untouched.
    assert (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").read_text(
        encoding="utf-8"
    ) == original


# -- JSONResultSaver --------------------------------------------------------


def test_json_saver_correct_values(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    data = json.loads(
        (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text(encoding="utf-8")
    )
    assert data["session_id"] == SESSION_ID
    assert data["test_type"] == TEST_TYPE
    assert {
        "session_id",
        "timestamp",
        "test_type",
        "records",
        "metadata",
    } <= data.keys()
    assert data["records"][0] == {"system": "sys_a", "item": "utt001", "rating": 4}
    assert data["metadata"] == {}


def test_json_saver_includes_metadata(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(
        SESSION_ID, TEST_TYPE, RATINGS, metadata=METADATA
    )
    data = json.loads(
        (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text(encoding="utf-8")
    )
    assert data["metadata"] == METADATA


def test_json_saver_includes_survey_as_separate_object(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(
        SESSION_ID,
        TEST_TYPE,
        RATINGS,
        metadata=METADATA,
        survey={"trial_count": "adequate"},
    )
    data = json.loads(
        (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text(encoding="utf-8")
    )
    assert data["survey"] == {"trial_count": "adequate"}
    assert data["metadata"] == METADATA


def test_json_saver_survey_defaults_to_empty_object(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    data = json.loads(
        (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text(encoding="utf-8")
    )
    assert data["survey"] == {}


def test_json_saver_each_session_is_separate_file(tmp_path):
    saver = JSONResultSaver(tmp_path, EXPERIMENT_ID)
    saver.save("sess-1", TEST_TYPE, RATINGS)
    saver.save("sess-2", TEST_TYPE, RATINGS)
    assert (tmp_path / EXPERIMENT_ID / "sess-1.json").exists()
    assert (tmp_path / EXPERIMENT_ID / "sess-2.json").exists()


def test_json_saver_refuses_to_overwrite_existing_session(tmp_path):
    saver = JSONResultSaver(tmp_path, EXPERIMENT_ID)
    saver.save(SESSION_ID, TEST_TYPE, RATINGS)
    original = (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text(
        encoding="utf-8"
    )
    with pytest.raises(ResultExistsError):
        saver.save(SESSION_ID, TEST_TYPE, [{"system": "x", "item": "y", "rating": 1}])
    assert (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text(
        encoding="utf-8"
    ) == original


# -- make_result_saver ------------------------------------------------------


def test_make_result_saver_returns_correct_type(tmp_path):
    assert isinstance(
        make_result_saver("csv", str(tmp_path), EXPERIMENT_ID), CSVResultSaver
    )
    assert isinstance(
        make_result_saver("json", str(tmp_path), EXPERIMENT_ID), JSONResultSaver
    )


def test_make_result_saver_raises_for_unknown_format(tmp_path):
    with pytest.raises(ValueError, match="Unknown output format"):
        make_result_saver("xml", str(tmp_path), EXPERIMENT_ID)


def test_result_saver_is_abstract():
    with pytest.raises(TypeError):
        ResultSaver()


# -- metrics ----------------------------------------------------------------
#
# Per-answer, unlike the session-constant metadata/survey - but stored the same
# way: nested under one key in JSON, flattened to prefixed columns in CSV.

METRIC_RATINGS = [
    {
        "system": "sys_a",
        "item": "utt001",
        "rating": 4,
        "metrics": {"response_time": 2.5},
    },
    {
        "system": "sys_b",
        "item": "utt002",
        "rating": 3,
        "metrics": {"response_time": 9.0},
    },
]


def test_csv_saver_writes_metrics_with_fixed_decimals(tmp_path):
    """A whole number keeps its decimals instead of collapsing to "9".

    str(float) would print 2.5 and 9.0 with different widths - and PHP's own
    float-to-string would print the latter as "9" - so the column is written
    to a fixed number of decimals on both sides instead.
    """
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID, metrics_keys=["response_time"])
    saver.save(SESSION_ID, TEST_TYPE, METRIC_RATINGS)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert [r["metrics_response_time"] for r in rows] == ["2.50", "9.00"]


def test_csv_saver_flattens_metrics_into_prefixed_columns_last(tmp_path):
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID, metrics_keys=["response_time"])
    saver.save(SESSION_ID, TEST_TYPE, METRIC_RATINGS)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    keys = list(rows[0].keys())
    assert keys[-1] == "metrics_response_time"
    assert keys.index("metrics_response_time") > keys.index("rating")
    assert rows[0]["metrics_response_time"] == "2.50"
    assert rows[1]["metrics_response_time"] == "9.00"
    # The nested dict itself must not leak out as a column of its own.
    assert "metrics" not in keys


def test_csv_saver_omits_metrics_columns_when_none_are_configured(tmp_path):
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert not [k for k in rows[0] if k.startswith("metrics")]


def test_json_saver_keeps_metrics_nested_in_each_record(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, METRIC_RATINGS)
    data = json.loads(
        (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text(encoding="utf-8")
    )
    assert data["records"][0]["metrics"] == {"response_time": 2.5}
    assert data["records"][1]["metrics"] == {"response_time": 9.0}
