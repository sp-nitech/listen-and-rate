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
    {"system": "sys_a", "utterance": "utt001", "rating": 4},
    {"system": "sys_b", "utterance": "utt002", "rating": 3},
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
        "utterance",
        "rating",
    }


def test_csv_saver_writes_correct_values(tmp_path):
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert len(rows) == 2
    assert rows[0]["session_id"] == SESSION_ID
    assert rows[0]["test_type"] == TEST_TYPE
    assert rows[0]["system"] == "sys_a"
    assert rows[0]["utterance"] == "utt001"
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
    assert (tmp_path / EXPERIMENT_ID / "session-1.csv").read_text().count(
        "session_id"
    ) == 1
    assert (tmp_path / EXPERIMENT_ID / "session-2.csv").read_text().count(
        "session_id"
    ) == 1


def test_csv_saver_creates_output_directory(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    CSVResultSaver(nested, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    assert (nested / EXPERIMENT_ID / f"{SESSION_ID}.csv").exists()


def test_csv_saver_infers_columns_from_ab_row_shape(tmp_path):
    ab_rows = [
        {"system_a": "A", "system_b": "B", "utterance": "u1", "winner": "A"},
        {"system_a": "A", "system_b": "B", "utterance": "u2", "winner": "tie"},
    ]
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, "ab", ab_rows)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert list(rows[0].keys()) == [
        "session_id",
        "timestamp",
        "test_type",
        "system_a",
        "system_b",
        "utterance",
        "winner",
    ]
    assert rows[0]["winner"] == "A"
    assert rows[1]["winner"] == "tie"


def test_csv_saver_infers_columns_from_abx_row_shape(tmp_path):
    abx_rows = [
        {"system_a": "A", "system_b": "B", "utterance": "u1", "correct": True},
        {"system_a": "A", "system_b": "B", "utterance": "u2", "correct": False},
    ]
    CSVResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, "abx", abx_rows)
    rows = list(csv.DictReader((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").open()))
    assert list(rows[0].keys()) == [
        "session_id",
        "timestamp",
        "test_type",
        "system_a",
        "system_b",
        "utterance",
        "correct",
    ]
    assert rows[0]["correct"] == "True"
    assert rows[1]["correct"] == "False"


def test_csv_saver_refuses_to_overwrite_existing_session(tmp_path):
    saver = CSVResultSaver(tmp_path, EXPERIMENT_ID)
    saver.save(SESSION_ID, TEST_TYPE, RATINGS)
    original = (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").read_text()
    with pytest.raises(ResultExistsError):
        saver.save(
            SESSION_ID, TEST_TYPE, [{"system": "x", "utterance": "y", "rating": 1}]
        )
    # The collected data must be left untouched.
    assert (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.csv").read_text() == original


# -- JSONResultSaver --------------------------------------------------------


def test_json_saver_correct_values(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    data = json.loads((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text())
    assert data["session_id"] == SESSION_ID
    assert data["test_type"] == TEST_TYPE
    assert {
        "session_id",
        "timestamp",
        "test_type",
        "ratings",
        "metadata",
    } <= data.keys()
    assert data["ratings"][0] == {"system": "sys_a", "utterance": "utt001", "rating": 4}
    assert data["metadata"] == {}


def test_json_saver_includes_metadata(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(
        SESSION_ID, TEST_TYPE, RATINGS, metadata=METADATA
    )
    data = json.loads((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text())
    assert data["metadata"] == METADATA


def test_json_saver_includes_survey_as_separate_object(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(
        SESSION_ID,
        TEST_TYPE,
        RATINGS,
        metadata=METADATA,
        survey={"trial_count": "adequate"},
    )
    data = json.loads((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text())
    assert data["survey"] == {"trial_count": "adequate"}
    assert data["metadata"] == METADATA


def test_json_saver_survey_defaults_to_empty_object(tmp_path):
    JSONResultSaver(tmp_path, EXPERIMENT_ID).save(SESSION_ID, TEST_TYPE, RATINGS)
    data = json.loads((tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text())
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
    original = (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text()
    with pytest.raises(ResultExistsError):
        saver.save(
            SESSION_ID, TEST_TYPE, [{"system": "x", "utterance": "y", "rating": 1}]
        )
    assert (tmp_path / EXPERIMENT_ID / f"{SESSION_ID}.json").read_text() == original


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
