"""The version check around the report."""

from __future__ import annotations

import json

import pytest

from listen_and_rate import __version__
from listen_and_rate.analysis._results import (
    ResultVersionMismatch,
    _read_result_file,
    _versions_in,
    version_difference_note,
)

from ._helpers import CSV_ROWS, _with_session_meta, _write_csv, generate_report_html


def _rows(version: str | None):
    rows = _with_session_meta("mos", CSV_ROWS)
    if version is None:
        return rows
    return [{"tool_version": version, **r} for r in rows]


def test_report_reads_files_that_agree_on_the_version(tmp_path):
    path = _write_csv(tmp_path / "a.csv", _rows(__version__))
    assert "<html" in generate_report_html([path]).lower()


def test_report_ignores_a_patch_level_difference(tmp_path):
    a = _write_csv(tmp_path / "a.csv", _rows("9.9.1"))
    b = _write_csv(tmp_path / "b.csv", _rows("9.9.7"))
    assert "<html" in generate_report_html([a, b]).lower()


def test_report_refuses_files_produced_by_different_versions(tmp_path):
    # Not a warning. Today the older file's rows are silently dropped, which
    # is a report missing a whole session with nothing to show for it.
    a = _write_csv(tmp_path / "a.csv", _rows("9.8.0"))
    b = _write_csv(tmp_path / "b.csv", _rows("9.9.0"))
    with pytest.raises(ValueError) as excinfo:
        generate_report_html([a, b])
    message = str(excinfo.value)
    assert "9.8" in message and "9.9" in message
    assert "a.csv" in message and "b.csv" in message


def test_report_refuses_to_mix_recorded_and_unrecorded_versions(tmp_path):
    a = _write_csv(tmp_path / "a.csv", _rows(None))
    b = _write_csv(tmp_path / "b.csv", _rows("9.9.0"))
    with pytest.raises(ValueError) as excinfo:
        generate_report_html([a, b])
    assert "unknown" in str(excinfo.value)


def test_report_accepts_files_that_all_predate_the_version_column(tmp_path):
    a = _write_csv(tmp_path / "a.csv", _rows(None))
    b = _write_csv(tmp_path / "b.csv", _rows(None))
    assert "<html" in generate_report_html([a, b]).lower()


def test_report_warns_when_the_results_predate_the_running_tool(tmp_path, caplog):
    path = _write_csv(tmp_path / "a.csv", _rows("9.9.0"))
    generate_report_html([path])
    assert "9.9.0" in caplog.text
    assert __version__ in caplog.text


def test_report_warns_when_the_results_record_no_version_at_all(tmp_path, caplog):
    # No column means the file was written before the version was recorded,
    # which is itself an older release. Staying silent there would leave the
    # oldest, most divergent results as the only unannounced ones.
    path = _write_csv(tmp_path / "a.csv", _rows(None))
    generate_report_html([path])
    assert "do not record which version" in caplog.text
    assert __version__ in caplog.text


def test_report_says_nothing_when_the_versions_match(tmp_path, caplog):
    path = _write_csv(tmp_path / "a.csv", _rows(__version__))
    generate_report_html([path])
    assert "version" not in caplog.text.lower()


def test_report_reads_a_php_written_file_whose_form_objects_are_empty(tmp_path):
    # PHP cannot tell an empty list from an empty map, so json_encode writes
    # "metadata": [] where the Python saver writes {}. Files like that are
    # already on disk, so the reader has to take both.
    path = tmp_path / "php.json"
    path.write_text(
        json.dumps(
            {
                "session_id": "s1",
                "timestamp": "2026-01-01",
                "test_type": "mos",
                "metadata": [],
                "survey": [],
                "records": [{"system": "A", "item": "i1", "rating": 4}],
            }
        ),
        encoding="utf-8",
    )
    assert "<html" in generate_report_html([path]).lower()


def test_version_note_stays_quiet_when_a_file_cannot_be_read(tmp_path):
    # The note runs while an exception is already in flight. Raising here
    # would replace the real failure with a second, less useful one.
    path = tmp_path / "broken.json"
    path.write_text("{ not json", encoding="utf-8")
    assert version_difference_note([path]) is None


def test_the_mismatch_message_summarizes_a_long_file_list(tmp_path):
    # A real study has one file per listener. Naming all of them turns the
    # message into a wall of uuids that hides the sentence explaining it.
    old = [_write_csv(tmp_path / f"old{i}.csv", _rows("9.8.0")) for i in range(9)]
    new = _write_csv(tmp_path / "new.csv", _rows("9.9.0"))
    with pytest.raises(ValueError) as excinfo:
        generate_report_html([*old, new])
    message = str(excinfo.value)
    assert "old0.csv" in message
    assert "old8.csv" not in message
    assert "6 more" in message


def test_the_mismatch_is_its_own_error_type(tmp_path):
    # The CLI skips the "may come from a version difference" note for it,
    # since the error already says exactly that.
    a = _write_csv(tmp_path / "a.csv", _rows("9.8.0"))
    b = _write_csv(tmp_path / "b.csv", _rows("9.9.0"))
    with pytest.raises(ResultVersionMismatch):
        generate_report_html([a, b])


def test_a_two_part_version_survives_the_csv_round_trip(tmp_path):
    # Left to infer, pandas reads a bare "1.10" as the float 1.1 and the
    # report would compare 1.1 against a release that never existed.
    path = _write_csv(tmp_path / "a.csv", _rows("1.10"))
    assert _versions_in(_read_result_file(path)) == {"1.10"}
