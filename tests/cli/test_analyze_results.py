"""Tests for the lar-report CLI."""

from __future__ import annotations

import csv
import logging
import re
import shutil
from pathlib import Path

import pytest

from .._helpers import write_config


def _run_analyze(monkeypatch, *args: str) -> None:
    """Run `lar-report` with the given extra CLI arguments."""
    monkeypatch.setattr("sys.argv", ["lar-report", *args])
    from listen_and_rate.cli.analyze_results import main

    main()


CSV_ROWS = [
    {
        "session_id": "s1",
        "timestamp": "2026-01-01",
        "test_type": "mos",
        "system": "A",
        "utterance": "u1",
        "rating": 4,
    },
    {
        "session_id": "s1",
        "timestamp": "2026-01-01",
        "test_type": "mos",
        "system": "B",
        "utterance": "u1",
        "rating": 3,
    },
]


def _write_csv(path: Path, rows: list[dict]) -> Path:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_analyze_results_writes_html(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    csv_path = _write_csv(tmp_path / "s1.csv", CSV_ROWS)
    out_path = tmp_path / "report.html"
    _run_analyze(monkeypatch, str(csv_path), "--output", str(out_path))
    assert out_path.exists()
    assert "<html>" in out_path.read_text(encoding="utf-8")


def test_analyze_report_saved_hint_is_logged_not_printed(
    tmp_path, monkeypatch, capsys, caplog
):
    """The 'Report saved' hint goes through logging.info, so it stays out of
    stdout/stderr and off-screen in tests (which don't emit INFO logs)."""
    pytest.importorskip("plotly")
    csv_path = _write_csv(tmp_path / "s1.csv", CSV_ROWS)
    out_path = tmp_path / "report.html"
    with caplog.at_level(logging.INFO, logger="listen_and_rate"):
        _run_analyze(monkeypatch, str(csv_path), "--output", str(out_path))

    assert any("Report saved" in record.message for record in caplog.records)
    captured = capsys.readouterr()
    assert "Report saved" not in captured.out
    assert "Report saved" not in captured.err


def test_analyze_results_with_directory(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _write_csv(results_dir / "s1.csv", CSV_ROWS)
    out_path = tmp_path / "report.html"
    _run_analyze(monkeypatch, str(results_dir), "--output", str(out_path))
    assert out_path.exists()


def test_analyze_results_missing_file_raises(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    with pytest.raises(FileNotFoundError):
        _run_analyze(monkeypatch, str(tmp_path / "none.csv"))


def test_analyze_results_default_output_next_to_results_dir(tmp_path, monkeypatch):
    """Without --output the report lands inside the results directory itself,
    so `make report-php` needs no explicit --output path."""
    pytest.importorskip("plotly")
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    _write_csv(results_dir / "s1.csv", CSV_ROWS)
    _run_analyze(monkeypatch, str(results_dir))
    assert (results_dir / "report.html").exists()


def test_analyze_results_default_output_next_to_result_files(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    csv_path = _write_csv(tmp_path / "s1.csv", CSV_ROWS)
    _run_analyze(monkeypatch, str(csv_path))
    assert (tmp_path / "report.html").exists()


def test_analyze_results_derives_results_dir_from_config(
    tmp_path, test_audio_file, monkeypatch
):
    """With no positional results argument, the results directory (and the
    default report location) come from --config's output.path - the FastAPI
    deployment's layout, where `make report CONFIG=...` should just work."""
    pytest.importorskip("plotly")
    config_yaml = write_config(
        tmp_path,
        {
            "test_type": "mos",
            "title": "T",
            "instructions": "I",
            "output": {"format": "csv", "path": str(tmp_path / "results")},
            "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
        },
    )
    results_dir = tmp_path / "results" / config_yaml.stem
    results_dir.mkdir(parents=True)
    _write_csv(results_dir / "s1.csv", CSV_ROWS)

    _run_analyze(monkeypatch, "--config", str(config_yaml))

    report = results_dir / "report.html"
    assert report.exists()
    assert "<html>" in report.read_text(encoding="utf-8")


def test_analyze_results_derived_dir_without_files_raises(
    tmp_path, test_audio_file, monkeypatch
):
    config_yaml = write_config(
        tmp_path,
        {
            "test_type": "mos",
            "title": "T",
            "instructions": "I",
            "output": {"format": "csv", "path": str(tmp_path / "results")},
            "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
        },
    )
    with pytest.raises(FileNotFoundError):
        _run_analyze(monkeypatch, "--config", str(config_yaml))


def test_analyze_results_without_results_or_config_exits_with_usage_error(
    tmp_path, monkeypatch, capsys
):
    with pytest.raises(SystemExit) as excinfo:
        _run_analyze(monkeypatch)
    assert excinfo.value.code == 2
    assert "--config" in capsys.readouterr().err


def test_analyze_results_root_resolves_output_path_under_root(
    tmp_path, test_audio_file, monkeypatch
):
    """--root is the deployment root: the config's (relative) output.path is
    resolved against it, so results are read from <root>/<output.path>/<config
    name> - the layout both deployments share now that save.php honors
    output.path too."""
    pytest.importorskip("plotly")
    config_yaml = write_config(
        tmp_path,
        {
            "test_type": "mos",
            "title": "T",
            "instructions": "I",
            # A non-default relative output.path proves --root resolution
            # honors output.path rather than assuming a "results" name.
            "output": {"format": "csv", "path": "./collected/"},
            "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
        },
    )
    deploy_root = tmp_path / "somewhere"
    results_dir = deploy_root / "collected" / config_yaml.stem
    results_dir.mkdir(parents=True)
    _write_csv(results_dir / "s1.csv", CSV_ROWS)

    _run_analyze(monkeypatch, "--config", str(config_yaml), "--root", str(deploy_root))

    report = results_dir / "report.html"
    assert report.exists()
    assert "<html>" in report.read_text(encoding="utf-8")


def test_analyze_results_root_with_absolute_output_path_exits_with_usage_error(
    tmp_path, test_audio_file, monkeypatch, capsys
):
    """An absolute output.path cannot be re-rooted - combining it with --root
    would silently ignore one of the two, so it is rejected instead."""
    config_yaml = write_config(
        tmp_path,
        {
            "test_type": "mos",
            "title": "T",
            "instructions": "I",
            "output": {"format": "csv", "path": str(tmp_path / "results")},
            "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
        },
    )
    with pytest.raises(SystemExit) as excinfo:
        _run_analyze(monkeypatch, "--config", str(config_yaml), "--root", str(tmp_path))
    assert excinfo.value.code == 2
    assert "absolute" in capsys.readouterr().err


def test_analyze_results_root_requires_config(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as excinfo:
        _run_analyze(monkeypatch, "--root", str(tmp_path))
    assert excinfo.value.code == 2
    assert "--config" in capsys.readouterr().err


def test_analyze_results_root_with_positional_results_exits_with_usage_error(
    tmp_path, test_audio_file, monkeypatch, capsys
):
    config_yaml = write_config(
        tmp_path,
        {
            "test_type": "mos",
            "title": "T",
            "instructions": "I",
            "output": {"format": "csv", "path": str(tmp_path / "results")},
            "stimuli": {"items": [{"id": "s001", "path": str(test_audio_file)}]},
        },
    )
    csv_path = _write_csv(tmp_path / "s1.csv", CSV_ROWS)
    with pytest.raises(SystemExit) as excinfo:
        _run_analyze(
            monkeypatch,
            str(csv_path),
            "--config",
            str(config_yaml),
            "--root",
            str(tmp_path),
        )
    assert excinfo.value.code == 2
    assert "--root" in capsys.readouterr().err


def test_analyze_results_config_flag_orders_systems(
    tmp_path, test_audio_file, monkeypatch
):
    """--config's stimuli_dirs.systems order should drive the report's
    system order, not alphabetical, when the two disagree."""
    pytest.importorskip("plotly")

    # Directories named so that ALPHABETICAL dir/system-name order would put
    # Alpha before Zebra - but the config lists Zebra first, and that's the
    # order the report should honor.
    d_zebra = tmp_path / "sys_zebra"
    d_alpha = tmp_path / "sys_alpha"
    d_zebra.mkdir()
    d_alpha.mkdir()
    shutil.copy(test_audio_file, d_zebra / "utt1.wav")
    shutil.copy(test_audio_file, d_alpha / "utt1.wav")
    config_yaml = write_config(
        tmp_path,
        {
            "test_type": "mos",
            "title": "T",
            "instructions": "I",
            "output": {"format": "csv", "path": str(tmp_path / "results")},
            "stimuli_dirs": {
                "systems": [
                    {"path": str(d_zebra), "system": "Zebra"},
                    {"path": str(d_alpha), "system": "Alpha"},
                ],
            },
        },
    )

    rows = [
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "mos",
            "system": "Zebra",
            "utterance": "u1",
            "rating": 4,
        },
        {
            "session_id": "s1",
            "timestamp": "t",
            "test_type": "mos",
            "system": "Alpha",
            "utterance": "u1",
            "rating": 3,
        },
    ]
    csv_path = _write_csv(tmp_path / "s.csv", rows)
    out_path = tmp_path / "report.html"
    _run_analyze(
        monkeypatch,
        str(csv_path),
        "--config",
        str(config_yaml),
        "--output",
        str(out_path),
    )
    html = out_path.read_text(encoding="utf-8")
    m = re.search(r'"x":\s*\[("Zebra",\s*"Alpha"|"Alpha",\s*"Zebra")\]', html)
    assert m, "could not find the MOS chart's system x-array in the report"
    assert m.group(1).startswith('"Zebra"')


# -- report config (--report-config) ----------------------------------------


def _write_report_config(tmp_path, data: dict) -> Path:
    return write_config(tmp_path, data, name="report-config.yaml")


def test_report_config_applies_labels_order_and_confidence(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    csv_path = _write_csv(tmp_path / "s.csv", CSV_ROWS)
    report_yaml = _write_report_config(
        tmp_path,
        {
            "confidence": 0.99,
            "order": ["B", "A"],
            "labels": {"A": "Proposed", "B": "Baseline"},
        },
    )
    out_path = tmp_path / "report.html"
    _run_analyze(
        monkeypatch,
        str(csv_path),
        "--report-config",
        str(report_yaml),
        "--output",
        str(out_path),
    )
    html = out_path.read_text(encoding="utf-8")
    assert '"x":["Baseline","Proposed"]' in html.replace(" ", "")
    assert "\u03b1=0.01" in html  # alpha follows confidence (1 - 0.99)


def test_report_config_scale_applies(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    csv_path = _write_csv(tmp_path / "s.csv", CSV_ROWS)
    report_yaml = _write_report_config(tmp_path, {"scale": {"width": 0.5}})
    out_path = tmp_path / "report.html"
    _run_analyze(
        monkeypatch,
        str(csv_path),
        "--report-config",
        str(report_yaml),
        "--output",
        str(out_path),
    )
    assert "max-width:450px" in out_path.read_text(encoding="utf-8")  # 900 * 0.5


def test_report_config_order_missing_system_raises(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    csv_path = _write_csv(tmp_path / "s.csv", CSV_ROWS)
    report_yaml = _write_report_config(tmp_path, {"order": ["A"]})  # missing B
    out_path = tmp_path / "report.html"
    with pytest.raises(ValueError, match="B"):
        _run_analyze(
            monkeypatch,
            str(csv_path),
            "--report-config",
            str(report_yaml),
            "--output",
            str(out_path),
        )


def test_report_config_is_optional(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    csv_path = _write_csv(tmp_path / "s.csv", CSV_ROWS)
    out_path = tmp_path / "report.html"
    _run_analyze(monkeypatch, str(csv_path), "--output", str(out_path))
    html = out_path.read_text(encoding="utf-8")
    assert "max-width:900px" in html  # default scale = 1.0
    assert "\u03b1=0.05" in html  # default confidence 0.95


def test_report_config_groups_render_stacked_sections(tmp_path, monkeypatch):
    pytest.importorskip("plotly")
    rows = [
        {
            "session_id": sid,
            "timestamp": "t",
            "test_type": "mos",
            "metadata_device": device,
            "system": system,
            "utterance": "u1",
            "rating": rating,
        }
        for sid, device, ratings in [
            ("s1", "Headphones", (4, 2)),
            ("s2", "Speakers", (5, 1)),
        ]
        for system, rating in zip(("A", "B"), ratings, strict=True)
    ]
    csv_path = _write_csv(tmp_path / "s.csv", rows)
    report_yaml = _write_report_config(
        tmp_path,
        {
            "groups": [
                {"label": "All listeners"},
                {"label": "Headphones", "metadata_filter": {"device": "Headphones"}},
            ]
        },
    )
    out_path = tmp_path / "report.html"
    _run_analyze(
        monkeypatch,
        str(csv_path),
        "--report-config",
        str(report_yaml),
        "--output",
        str(out_path),
    )
    html = out_path.read_text(encoding="utf-8")
    assert html.count("<h2") == 3  # 2 group sections + trailing Participants
    assert "All listeners" in html
    assert "Headphones" in html
    assert "Participants" in html
