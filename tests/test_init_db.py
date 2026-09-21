"""Unit-Tests fuer die MongoDB-Umstellung (keine DB-Verbindung noetig).

Der fruehere SQLite-Schema-/Migrationstest ist obsolet: init_db() legt jetzt nur
noch MongoDB-Indizes an (ensure_indexes()). Diese Tests pruefen die reinen
Hilfsfunktionen der neuen Datenschicht ohne laufende Datenbank.
"""

from types import SimpleNamespace
from unittest.mock import patch

import app as app_module
from db_mongo import oid
from bson import ObjectId


def test_new_user_defaults_has_full_schema_field_set():
    d = app_module._new_user_defaults()
    # Felder, die unter SQLite NOT NULL DEFAULT-Werte hatten, muessen vorhanden
    # sein, damit row["feld"]-Zugriffe unter MongoDB kein KeyError werfen.
    for field in (
        "role", "display_name", "onboarded", "banned", "banned_message",
        "school", "class_name", "notify_laden_email", "avatar_url", "iserv_email",
    ):
        assert field in d
    # Alle Fach-Level und Verifizierungsflags sind gesetzt.
    for col in app_module.CHAT_LEVEL_COLUMN.values():
        assert d[col] == "noob"
    for col in app_module.CHAT_VERIFIED_COLUMN.values():
        assert d[col] == 0


def test_oid_parses_valid_and_rejects_invalid():
    real = ObjectId()
    assert oid(str(real)) == real
    assert oid(real) == real
    assert oid("not-an-objectid") is None
    assert oid("") is None
    assert oid(None) is None


def test_admin_and_dev_can_use_chat_room_without_pro():
    user_id = ObjectId()

    class Users:
        def __init__(self, role):
            self.role = role

        def find_one(self, query, fields=None):
            return {"_id": user_id, "role": self.role, "level_math": "noob"}

    class Presence:
        def count_documents(self, query):
            return 0

    fake_db = SimpleNamespace(users=Users("admin"), chat_presence=Presence())
    assert app_module._chat_may_use_room(fake_db, str(user_id), "math") is True

    fake_db.users = Users("dev")
    assert app_module._chat_may_use_room(fake_db, str(user_id), "math") is True


def test_admin_can_join_closed_room():
    uid = str(ObjectId())
    fake_db = SimpleNamespace(
        chat_appointments=SimpleNamespace(find_one=lambda *args, **kwargs: {"started": 1}),
        chat_presence=SimpleNamespace(
            find_one=lambda *args, **kwargs: None,
            insert_one=lambda *args, **kwargs: None,
            update_one=lambda *args, **kwargs: None,
        ),
    )

    with app_module.app.test_request_context("/api/chat/join", method="POST", json={"subject": "math"}):
        app_module.session.clear()
        app_module.session["user_id"] = uid
        app_module.session["username"] = "admin-user"
        app_module.session["role"] = "admin"

        with patch.object(app_module, "get_db", return_value=fake_db), \
             patch.object(app_module, "user_may_access_subject", return_value=True), \
             patch.object(app_module, "_user_level_for_subject", return_value="noob"), \
             patch.object(app_module, "_user_role_for_chat", return_value="admin"):
            response = app_module.chat_join.__wrapped__()

    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_delete_chat_subject_data_clears_matching_subjects():
    deleted = {}

    class FakeCollection:
        def delete_many(self, filt):
            deleted.setdefault(self.name, []).append(filt)
            return SimpleNamespace(deleted_count=1)

    db = SimpleNamespace(
        chat_presence=FakeCollection(),
        chat_messages=FakeCollection(),
        chat_appointments=FakeCollection(),
        chat_ratings=FakeCollection(),
        chat_message_reports=FakeCollection(),
    )
    for collection in (db.chat_presence, db.chat_messages, db.chat_appointments,
                       db.chat_ratings, db.chat_message_reports):
        collection.name = collection.__class__.__name__

    app_module.delete_chat_subject_data(db, "german")

    assert any("german" in str(filt) for filt in deleted.get("FakeCollection", []))


def test_invite_codes_pdf_is_valid_and_contains_codes_on_multiple_pages():
    rows = [
        {"_id": f"code-{index:02d}", "school": "Testschule", "class_name": "1b"}
        for index in range(25)
    ]

    payload = app_module._invite_codes_pdf(rows)

    assert payload.startswith(b"%PDF-1.4")
    assert payload.endswith(b"%%EOF\n")
    assert b"code-00" in payload
    assert b"code-24" in payload
    assert b"/Count 2" in payload


def test_invite_codes_pdf_escapes_pdf_control_characters():
    payload = app_module._invite_codes_pdf([
        {"_id": r"abc(123)\\", "school": "Schule (Nord)", "class_name": "1b"}
    ])

    assert b"abc\\(123\\)" in payload
    assert b"Schule \\(Nord\\) / 1b" in payload


def test_learning_place_update_is_limited_to_owner():
    user_id = ObjectId()
    place_id = ObjectId()
    recorded = {}

    class LearningPlaces:
        def update_one(self, query, update):
            recorded["query"] = query
            recorded["update"] = update
            return SimpleNamespace(matched_count=1)

    fake_db = SimpleNamespace(learning_places=LearningPlaces())
    with app_module.app.test_request_context(
        f"/api/learning-places/{place_id}",
        method="PUT",
        json={"name": "  Neue   Bibliothek  ", "address": " Raum 2 ", "note": " Ruhig "},
    ):
        app_module.session["user_id"] = str(user_id)
        with patch.object(app_module, "get_db", return_value=fake_db):
            response = app_module.learning_places_update.__wrapped__(str(place_id))

    assert response.status_code == 200
    assert recorded["query"] == {"_id": place_id, "user_id": user_id}
    assert recorded["update"]["$set"]["name"] == "Neue Bibliothek"
    assert recorded["update"]["$set"]["address"] == "Raum 2"
    assert recorded["update"]["$set"]["note"] == "Ruhig"


def test_learning_place_update_rejects_non_owner():
    place_id = ObjectId()

    class LearningPlaces:
        def update_one(self, query, update):
            return SimpleNamespace(matched_count=0)

    fake_db = SimpleNamespace(learning_places=LearningPlaces())
    with app_module.app.test_request_context(
        f"/api/learning-places/{place_id}",
        method="PUT",
        json={"name": "Fremder Lernort"},
    ):
        app_module.session["user_id"] = str(ObjectId())
        with patch.object(app_module, "get_db", return_value=fake_db):
            response, status = app_module.learning_places_update.__wrapped__(str(place_id))

    assert status == 404
    assert response.get_json()["error"] == "not_found"


def test_level_increase_quiz_is_required_and_checked():
    row = {
        "school": "Testschule",
        "class_name": "8a",
        **{column: "noob" for column in app_module.CHAT_LEVEL_COLUMN.values()},
    }
    levels = tuple(
        "medium" if subject == "math" else "noob"
        for subject in app_module.CHAT_SUBJECT_ORDER
    )
    questions = [
        {"correct": 0}, {"correct": 1}, {"correct": 2},
        {"correct": 0}, {"correct": 1},
    ]

    with patch.object(app_module, "_resolve_quiz_questions", return_value=questions):
        assert app_module._validate_level_increase_quiz(None, row, levels, {}) == "level_quiz_required"
        assert app_module._validate_level_increase_quiz(
            None, row, levels, {"math": [2, 2, 2, 2, 2]}
        ) == "level_quiz_failed"
        assert app_module._validate_level_increase_quiz(
            None, row, levels, {"math": [0, 1, 2, 2, 2]}
        ) is None


def test_unchanged_or_lower_levels_do_not_require_quiz():
    row = {
        **{column: "medium" for column in app_module.CHAT_LEVEL_COLUMN.values()},
    }
    unchanged = tuple("medium" for _ in app_module.CHAT_SUBJECT_ORDER)
    lower = tuple("noob" for _ in app_module.CHAT_SUBJECT_ORDER)

    assert app_module._validate_level_increase_quiz(None, row, unchanged, None) is None
    assert app_module._validate_level_increase_quiz(None, row, lower, None) is None


def test_onboarding_uses_three_questions_per_subject():
    assert app_module.ONBOARDING_QUIZ_QUESTION_COUNT == 3
    assert app_module.ONBOARDING_QUIZ_MIN_CORRECT == {"pro": 2, "medium": 1}
