"""Tests for the pair_survey /api/config and /api/submit endpoints."""

from __future__ import annotations

import json

from ._helpers import _pair_survey_client, _pair_survey_questions


def _ids(trial):
    return [trial["source"]["id"], trial["generated"]["id"]]


def test_pair_survey_config_returns_questions_and_trials(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch) as tc:
        data = tc.get("/api/config").json()
        assert data["test_type"] == "pair_survey"
        assert [q["key"] for q in data["questions"]] == ["naturalness", "similarity"]
        assert "scope" not in data["questions"][0]
        assert data["source_label"] == "Source"
        assert data["generated_label"] == "Generated"
        assert len(data["trials"]) == 2
        trial = data["trials"][0]
        assert trial["source"]["id"].startswith("A__")
        assert trial["generated"]["id"].startswith("B__")
        assert "stimuli" not in trial


def test_pair_survey_config_includes_question_description(
    tmp_path, test_audio_file, monkeypatch
):
    questions = _pair_survey_questions()
    questions[0]["description"] = "How natural does the speech sound?"
    with _pair_survey_client(
        tmp_path, test_audio_file, monkeypatch, questions=questions
    ) as tc:
        data = tc.get("/api/config").json()
        first, second = data["questions"]
        assert first["description"] == "How natural does the speech sound?"
        assert second["description"] == ""


def test_pair_survey_config_includes_question_help(
    tmp_path, test_audio_file, monkeypatch
):
    questions = _pair_survey_questions()
    questions[0]["help"] = {5: "Sounds human"}
    with _pair_survey_client(
        tmp_path, test_audio_file, monkeypatch, questions=questions
    ) as tc:
        data = tc.get("/api/config").json()
        first, second = data["questions"]
        assert first["help"]["5"] == "Sounds human"
        assert second["help"] == {}


def test_pair_survey_config_custom_player_labels(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        source_label="Original",
        generated_label="Anonymized",
    ) as tc:
        data = tc.get("/api/config").json()
        assert data["source_label"] == "Original"
        assert data["generated_label"] == "Anonymized"


def test_pair_survey_config_hides_system_names(tmp_path, test_audio_file, monkeypatch):
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch) as tc:
        text = json.dumps(tc.get("/api/config").json())
        assert "item" not in text
        assert "system" not in text
        assert '"A"' not in text
        assert '"B"' not in text


def test_pair_survey_config_filters_by_rater(tmp_path, test_audio_file, monkeypatch):
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=3,
        assignments={"alice": ["utt0", "utt1"], "bob": ["utt2"]},
    ) as tc:
        alice = tc.get("/api/config", params={"rater": "alice"}).json()["trials"]
        bob = tc.get("/api/config", params={"rater": "bob"}).json()["trials"]
        alice_items = {t["generated"]["id"].split("__")[1] for t in alice}
        bob_items = {t["generated"]["id"].split("__")[1] for t in bob}
        assert alice_items == {"utt0", "utt1"}
        assert bob_items == {"utt2"}


def test_pair_survey_unknown_rater_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        assignments={"alice": ["utt0"]},
        n_items=1,
    ) as tc:
        res = tc.get("/api/config", params={"rater": "nobody"})
        assert res.status_code == 400
        assert "Unknown rater" in res.json()["detail"]


def test_pair_survey_missing_rater_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        assignments={"alice": ["utt0"]},
        n_items=1,
    ) as tc:
        res = tc.get("/api/config")
        assert res.status_code == 400
        assert "rater" in res.json()["detail"]


def test_pair_survey_unknown_rater_allowed_when_not_required(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=2,
        assignments={"alice": ["utt0"]},
        require_known_rater=False,
    ) as tc:
        data = tc.get("/api/config", params={"rater": "nobody"}).json()
        assert len(data["trials"]) == 2


def test_pair_survey_submit_happy_path(tmp_path, test_audio_file, monkeypatch):
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        ids = _ids(tc.get("/api/config").json()["trials"][0])
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "answers": {"naturalness": "5", "similarity": "4"},
                    }
                ],
            },
        )
        assert res.status_code == 200
        saved = json.loads((tmp_path / "results" / "config" / "s1.json").read_text())
        row = saved["records"][0]
        assert row["naturalness"] == 5
        assert row["similarity"] == 4
        assert row["item"] == "utt0"
        assert row["system"] == "B"
        assert row["reference"] == "A"
        assert saved["complete"] is True


def _choice(trial, naturalness="5", similarity="4"):
    return {
        "stimulus_ids": _ids(trial),
        "answers": {"naturalness": naturalness, "similarity": similarity},
    }


def test_pair_survey_partial_submit_grows_the_session_file(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch, n_items=2) as tc:
        trials = tc.get("/api/config").json()["trials"]
        path = tmp_path / "results" / "config" / "s1.json"
        first = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "complete": False,
                "choices": [_choice(trials[0])],
            },
        )
        assert first.status_code == 200
        saved = json.loads(path.read_text())
        assert saved["complete"] is False
        assert len(saved["records"]) == 1

        second = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "complete": False,
                "choices": [_choice(trials[0]), _choice(trials[1], "3", "2")],
            },
        )
        assert second.status_code == 200
        saved = json.loads(path.read_text())
        assert saved["complete"] is False
        assert len(saved["records"]) == 2
        assert saved["records"][1]["naturalness"] == 3

        finish = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "complete": True,
                "choices": [_choice(trials[0]), _choice(trials[1], "3", "2")],
            },
        )
        assert finish.status_code == 200
        saved = json.loads(path.read_text())
        assert saved["complete"] is True
        assert len(saved["records"]) == 2


def test_pair_survey_incomplete_skips_required_survey(
    tmp_path, test_audio_file, monkeypatch
):
    survey = {
        "fields": [
            {
                "key": "trial_count",
                "label": "Was the number of trials appropriate?",
                "type": "select",
                "options": ["TooFew", "Appropriate", "TooMany"],
                "required": True,
            }
        ]
    }
    with _pair_survey_client(
        tmp_path, test_audio_file, monkeypatch, n_items=1, survey=survey
    ) as tc:
        trial = tc.get("/api/config").json()["trials"][0]
        partial = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "complete": False,
                "choices": [_choice(trial)],
            },
        )
        assert partial.status_code == 200
        finish = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "complete": True,
                "choices": [_choice(trial)],
            },
        )
        assert finish.status_code == 400
        assert "trial_count" in finish.json()["detail"]


def test_pair_survey_submit_rejects_reversed_ids(
    tmp_path, test_audio_file, monkeypatch
):
    """Generated then source is not a valid [source, generated] pair."""
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        source_id, generated_id = _ids(tc.get("/api/config").json()["trials"][0])
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "choices": [
                    {
                        "stimulus_ids": [generated_id, source_id],
                        "answers": {"naturalness": "3", "similarity": "3"},
                    }
                ],
            },
        )
        assert res.status_code == 400
        assert "source" in res.json()["detail"]


def test_pair_survey_submit_stores_rater_in_metadata(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=1,
        assignments={"alice": ["utt0"]},
    ) as tc:
        ids = _ids(tc.get("/api/config", params={"rater": "alice"}).json()["trials"][0])
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "rater": "alice",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "answers": {"naturalness": "3", "similarity": "2"},
                    }
                ],
            },
        )
        assert res.status_code == 200
        saved = json.loads((tmp_path / "results" / "config" / "s1.json").read_text())
        assert saved["metadata"]["rater"] == "alice"


def test_pair_survey_submit_unknown_rater_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(
        tmp_path,
        test_audio_file,
        monkeypatch,
        n_items=1,
        assignments={"alice": ["utt0"]},
    ) as tc:
        ids = _ids(tc.get("/api/config", params={"rater": "alice"}).json()["trials"][0])
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "rater": "nobody",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "answers": {"naturalness": "3", "similarity": "2"},
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_pair_survey_missing_required_answer_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        ids = _ids(tc.get("/api/config").json()["trials"][0])
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "choices": [{"stimulus_ids": ids, "answers": {}}],
            },
        )
        assert res.status_code == 400
        assert "naturalness" in res.json()["detail"]


def test_pair_survey_out_of_range_answer_returns_400(
    tmp_path, test_audio_file, monkeypatch
):
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        ids = _ids(tc.get("/api/config").json()["trials"][0])
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "answers": {"naturalness": "3", "similarity": "9"},
                    }
                ],
            },
        )
        assert res.status_code == 400


def test_pair_survey_empty_choices_returns_400(tmp_path, test_audio_file, monkeypatch):
    with _pair_survey_client(tmp_path, test_audio_file, monkeypatch, n_items=1) as tc:
        res = tc.post(
            "/api/submit", json={"session_id": "s1", "test_type": "pair_survey"}
        )
        assert res.status_code == 400


def test_pair_survey_choice_question_round_trips(
    tmp_path, test_audio_file, monkeypatch
):
    questions = _pair_survey_questions()
    questions.append(
        {
            "key": "preference",
            "label": "Which is closer to the target?",
            "type": "choice",
            "options": ["A", "B", "About the same"],
        }
    )
    with _pair_survey_client(
        tmp_path, test_audio_file, monkeypatch, n_items=1, questions=questions
    ) as tc:
        ids = _ids(tc.get("/api/config").json()["trials"][0])
        res = tc.post(
            "/api/submit",
            json={
                "session_id": "s1",
                "test_type": "pair_survey",
                "choices": [
                    {
                        "stimulus_ids": ids,
                        "answers": {
                            "naturalness": "3",
                            "similarity": "4",
                            "preference": "About the same",
                        },
                    }
                ],
            },
        )
        assert res.status_code == 200
        row = json.loads((tmp_path / "results" / "config" / "s1.json").read_text())[
            "records"
        ][0]
        assert row["preference"] == "About the same"
