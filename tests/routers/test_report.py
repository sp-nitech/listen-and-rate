"""Tests for the /report route."""

from __future__ import annotations

import csv

import pytest


def test_report_no_results_returns_no_data_page(client):
    res = client.get("/report")
    assert res.status_code == 200
    assert "No results yet" in res.text


def test_report_with_results_returns_html(client, config_yaml):
    pytest.importorskip("plotly")
    results_dir = config_yaml.parent / "results" / "config"
    results_dir.mkdir(parents=True, exist_ok=True)
    rows = [
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
    with open(results_dir / "s1.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    res = client.get("/report")
    assert res.status_code == 200
    assert "<html>" in res.text
