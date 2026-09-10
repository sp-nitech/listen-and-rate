"""Tests for GET /progress and GET /api/progress."""

from __future__ import annotations

import json

from .api._helpers import _pair_survey_client


def _ids(trial):
    return [trial["source"]["id"], trial["generated"]["id"]]


def _choice(trial, naturalness="5", similarity="4"):
    return {
        "stimulus_ids": _ids(trial),
        "answers": {"naturalness": naturalness, "similarity": similarity},
    }


def test_progress_no_assignments_and_no_results(client):
    data = client.get("/api/progress").json()
    assert data["raters"] == []
    res = client.get("/progress")
    assert res.status_code == 200
    assert "No assignments" in res.text


def test_progress_tracks_partial_and_complete_raters(
    tmp_path, test_audio_file, monkeypatch
):
    assignments = {"alice": ["utt0", "utt1"], "bob": ["utt0"]}
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=2,
        assignments=assignments,
    ) as tc:
        empty = tc.get("/api/progress").json()
        by = {r["rater"]: r for r in empty["raters"]}
        assert by["alice"]["status"] == "not_started"
        assert by["alice"]["assigned_count"] == 2
        assert by["alice"]["completed_count"] == 0
        assert by["bob"]["status"] == "not_started"

        trials = tc.get("/api/config", params={"rater": "alice"}).json()["trials"]
        assert len(trials) == 2
        partial = tc.post(
            "/api/submit",
            json={
                "session_id": "alice-s1",
                "test_type": "pair_survey",
                "rater": "alice",
                "complete": False,
                "choices": [_choice(trials[0])],
            },
        )
        assert partial.status_code == 200

        mid = tc.get("/api/progress").json()
        alice = {r["rater"]: r for r in mid["raters"]}["alice"]
        bob = {r["rater"]: r for r in mid["raters"]}["bob"]
        assert alice["status"] == "in_progress"
        assert alice["completed_count"] == 1
        assert alice["awaiting_finish"] is False
        assert bob["status"] == "not_started"
        done_items = [i["item"] for i in alice["items"] if i["status"] == "done"]
        pending = [i["item"] for i in alice["items"] if i["status"] == "pending"]
        assert done_items == ["utt0"]
        assert pending == ["utt1"]
        assert alice["items"][0]["answers"]["naturalness"] == 5

        finish = tc.post(
            "/api/submit",
            json={
                "session_id": "alice-s1",
                "test_type": "pair_survey",
                "rater": "alice",
                "complete": True,
                "choices": [_choice(trials[0]), _choice(trials[1], "2", "3")],
            },
        )
        assert finish.status_code == 200
        done = tc.get("/api/progress").json()
        alice = {r["rater"]: r for r in done["raters"]}["alice"]
        assert alice["status"] == "complete"
        assert alice["completed_count"] == 2
        assert alice["awaiting_finish"] is False

        html = tc.get("/progress")
        assert html.status_code == 200
        assert "alice" in html.text
        assert "bob" in html.text
        assert "Complete" in html.text
        assert "Not started" in html.text
        assert "naturalness=5" in html.text


def test_progress_lists_unassigned_raters_from_result_files(
    tmp_path, test_audio_file, monkeypatch
):
    assignments = {"alice": ["utt0"]}
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=1,
        assignments=assignments,
        require_known_rater=False,
    ) as tc:
        results_dir = tmp_path / "results" / "config"
        results_dir.mkdir(parents=True, exist_ok=True)
        (results_dir / "stray.json").write_text(
            json.dumps(
                {
                    "session_id": "stray",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "test_type": "pair_survey",
                    "complete": True,
                    "metadata": {"rater": "dave"},
                    "survey": {},
                    "records": [
                        {
                            "system": "B",
                            "item": "utt0",
                            "reference": "A",
                            "naturalness": 1,
                            "similarity": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        data = tc.get("/api/progress").json()
        by = {r["rater"]: r for r in data["raters"]}
        assert by["alice"]["in_assignments"] is True
        assert by["dave"]["in_assignments"] is False
        assert by["dave"]["completed_count"] == 1
        html = tc.get("/progress")
        assert "Unassigned sessions" in html.text
        assert "dave" in html.text
