from unittest.mock import patch

import mongomock
import pytest

import app as app_module


@pytest.mark.parametrize("level", ["noob", "medium"])
def test_onboarding_lower_levels_need_no_answers(level):
    db = mongomock.MongoClient().test
    uid = db.users.insert_one({"username": "learner"}).inserted_id
    levels = {subject: level for subject in app_module.CHAT_SUBJECT_ORDER}
    with app_module.app.test_request_context("/api/onboarding/confirm", method="POST", json={
        "display_name": "Learner", "class_name": "8a", "levels": levels,
    }):
        app_module.session["user_id"] = str(uid)
        with patch.object(app_module, "_load_api_auth_context", return_value=True), \
             patch.object(app_module, "get_db", return_value=db), \
             patch.object(app_module, "_resolve_quiz_questions") as questions:
            response = app_module.api_onboarding_confirm()
        questions.assert_not_called()
    assert response.status_code == 200
    assert response.get_json()["levels"] == levels
    assert response.get_json()["notes"] == []
    saved = db.users.find_one({"_id": uid})
    assert saved["onboarded"] == 1
    assert all(saved[column] == level for column in app_module.CHAT_LEVEL_COLUMN.values())


@pytest.mark.parametrize("answers, expected", [([], "medium"), ([0, 1, 0], "medium"), ([0, 0, 1], "pro")])
def test_onboarding_checks_only_pro_in_mixed_levels(answers, expected):
    db = mongomock.MongoClient().test
    uid = db.users.insert_one({"username": "learner"}).inserted_id
    levels = {subject: "medium" for subject in app_module.CHAT_SUBJECT_ORDER}
    levels.update(math="pro", art="noob")
    with app_module.app.test_request_context("/api/onboarding/confirm", method="POST", json={
        "display_name": "Learner", "class_name": "8a", "levels": levels,
        "quiz_answers": {"math": answers},
    }):
        app_module.session["user_id"] = str(uid)
        with patch.object(app_module, "_load_api_auth_context", return_value=True), \
             patch.object(app_module, "get_db", return_value=db), \
             patch.object(app_module, "_resolve_quiz_questions", return_value=[
                 {"correct": 0}, {"correct": 0}, {"correct": 1},
             ]) as questions:
            response = app_module.api_onboarding_confirm()
        questions.assert_called_once_with(db, "", "8a", "math")
    assert response.status_code == 200
    assert response.get_json()["levels"] == {**levels, "math": expected}
    assert db.users.find_one({"_id": uid})["level_math"] == expected
