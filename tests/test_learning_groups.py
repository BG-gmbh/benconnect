from unittest.mock import patch

import mongomock
import pytest
from bson import ObjectId

import app as app_module


@pytest.fixture
def chat():
    db = mongomock.MongoClient().test
    users = {}
    for name, level in (("pro", "pro"), ("learner", "medium"), ("outsider", "pro")):
        users[name] = db.users.insert_one({
            "username": name, "role": "user", "level_math": level,
        }).inserted_id
    client = app_module.app.test_client()

    def request(name, path, data=None):
        with client.session_transaction() as session:
            session["user_id"] = str(users[name])
            session["username"] = name
            session["role"] = "user"
        with patch.object(app_module, "get_db", return_value=db):
            return client.get(path) if data is None else client.post(path, json=data)

    return db, users, request


def save_group(request):
    for name in ("pro", "learner"):
        assert request(name, "/api/chat/join", {"subject": "math"}).status_code == 200
    response = request("learner", "/api/chat/learning-groups", {
        "subject": "math", "name": "  Mathe-Team  ",
    })
    assert response.status_code == 201
    return "math:group-" + response.json["id"]


def test_group_survives_empty_chat_and_supports_a_new_session(chat):
    db, users, request = chat
    room = save_group(request)
    group = db.learning_groups.find_one()
    assert group["name"] == "Mathe-Team"
    assert set(group["member_ids"]) == {users["pro"], users["learner"]}
    assert request("pro", "/api/chat/leave", {"subject": "math"}).status_code == 200
    assert db.chat_presence.count_documents({}) == 0
    for name in ("pro", "learner"):
        listed = request(name, "/api/chat/learning-groups").json["groups"]
        assert listed[0]["room"] == room
        assert listed[0]["members"] == ["learner", "pro"]
    assert request("learner", "/api/chat/join", {"subject": room}).json["error"] == "need_pro"
    assert request("pro", "/api/chat/join", {"subject": room}).status_code == 200
    assert request("learner", "/api/chat/join", {"subject": room}).status_code == 200
    assert request("learner", "/api/chat/send", {"subject": room, "body": "Hallo Team"}).status_code == 200
    assert request("pro", "/api/chat/messages?subject=" + room).json["messages"][0]["body"] == "Hallo Team"
    rooms = request("learner", "/api/chat/rooms").json["rooms"]
    assert rooms[0]["label"] == "Mathe-Team"
    assert request("pro", "/api/chat/appointment", {
        "subject": room, "appointment": "2026-10-01 15:00", "location": "Bibliothek",
    }).status_code == 200
    assert request("learner", "/api/chat/appointment?subject=" + room).json["location"] == "Bibliothek"
    assert request("pro", "/api/chat/leave", {"subject": room}).status_code == 200
    assert db.chat_messages.count_documents({"subject": room}) == 0
    assert db.learning_groups.count_documents({}) == 1
    assert request("pro", "/api/chat/join", {"subject": room}).status_code == 200
    assert request("pro", "/api/chat/messages?subject=" + room).json["messages"] == []


def test_non_members_cannot_discover_or_use_saved_group(chat):
    db, users, request = chat
    room = save_group(request)
    assert request("pro", "/api/chat/join", {"subject": room}).status_code == 200
    assert request("outsider", "/api/chat/learning-groups").json == {"groups": []}
    assert all(r["subject"] != room for r in request("outsider", "/api/chat/rooms").json["rooms"])
    for path, data in (
        ("/api/chat/join", {"subject": room}),
        ("/api/chat/send", {"subject": room, "body": "No access"}),
        ("/api/chat/learning-groups", {"subject": room, "name": "Stolen group"}),
        ("/api/chat/appointment", {"subject": room, "appointment": "2026-10-01 15:00", "location": "X"}),
        ("/api/chat/appointment/start", {"subject": room}),
        ("/api/chat/appointment/end", {"subject": room}),
        ("/api/chat/messages?subject=" + room, None),
        ("/api/chat/appointment?subject=" + room, None),
    ):
        assert request("outsider", path, data).status_code == 400


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, 123, None])
def test_invalid_group_names_are_rejected(chat, name):
    db, users, request = chat
    assert request("pro", "/api/chat/learning-groups", {"subject": "math", "name": name}).status_code == 400
    assert db.learning_groups.count_documents({}) == 0


def test_saving_requires_presence_and_server_selects_members(chat):
    db, users, request = chat
    assert request("pro", "/api/chat/learning-groups", {"subject": "math", "name": "Team"}).status_code == 403
    request("pro", "/api/chat/join", {"subject": "math"})
    assert request("pro", "/api/chat/learning-groups", {
        "subject": "math", "name": "Team", "member_ids": [str(users["outsider"])],
    }).status_code == 201
    assert db.learning_groups.find_one()["member_ids"] == [users["pro"]]
    assert request("pro", "/api/chat/join", {"subject": "math:group-" + str(ObjectId())}).status_code == 400


def test_group_endpoints_require_login():
    client = app_module.app.test_client()
    assert client.get("/api/chat/learning-groups").status_code == 401
    assert client.post("/api/chat/learning-groups", json={}).status_code == 401
