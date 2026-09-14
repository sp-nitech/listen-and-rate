"""Tests for the /report route."""

from __future__ import annotations

import csv


def test_report_no_results_returns_no_data_page(client):
    res = client.get("/report")
    assert res.status_code == 200
    assert "No results yet" in res.text


def test_report_with_results_returns_html(client, config_yaml):
    results_dir = config_yaml.parent / "results" / "config"
    results_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "session_id": "s1",
            "timestamp": "2026-01-01",
            "test_type": "mos",
            "system": "A",
            "item": "u1",
            "rating": 4,
        },
        {
            "session_id": "s1",
            "timestamp": "2026-01-01",
            "test_type": "mos",
            "system": "B",
            "item": "u1",
            "rating": 3,
        },
    ]
    with open(results_dir / "s1.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    res = client.get("/report")
    assert res.status_code == 200
    assert "<html>" in res.text


def test_report_of_a_sequence_links_each_test_report(
    tmp_path, test_audio_file, monkeypatch
):
    # A sequence holds one report per test, so the page without a stage named
    # lists them rather than guessing which one was meant.
    from .api._helpers import _sequence_client

    with _sequence_client(tmp_path, test_audio_file, monkeypatch) as client:
        index = client.get("/report")
        assert index.status_code == 200
        assert 'href="report?stage=a"' in index.text
        assert 'href="report?stage=b"' in index.text
        assert "No results yet" in client.get("/report", params={"stage": "b"}).text
