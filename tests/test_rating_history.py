from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import mongomock
import pytest

import app as app_module


@pytest.fixture
def ratings():
    db = mongomock.MongoClient(tz_aware=True).test
    uid = db.users.insert_one({"username": "Pro", "role": "dev", "level_math": "pro"}).inserted_id
    db.chat_presence.insert_one({"subject": "math", "user_id": uid, "level": "pro"})
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    db.chat_appointments.insert_one({
        "_id": "math", "appointment": "2026-09-30 10:00", "location": "Bibliothek",
        "started": 1, "ended": 1, "started_at": start, "ended_at": start + timedelta(minutes=45),
    })
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=str(uid), username="Pro", role="dev")
    with patch.object(app_module, "get_db", return_value=db):
        yield db, uid, client


def rate(client, stars=5):
    response = client.post('/api/chat/appointment/rate', json={"subject": "math", "rating": stars, "comment": "Gutes Treffen"})
    assert response.status_code == 200


def test_rating_is_archived_immediately_and_survives_leaving(ratings):
    db, uid, client = ratings
    rate(client)
    assert db.appointment_ratings.count_documents({}) == 1
    assert len(client.get('/api/admin/ratings').json['ratings']) == 1
    assert client.post('/api/chat/leave', json={"subject": "math"}).status_code == 200
    assert db.chat_ratings.count_documents({}) == 0
    assert db.chat_appointments.count_documents({}) == 0
    rows = client.get('/api/admin/ratings').json['ratings']
    assert len(rows) == 1
    assert rows[0]['rating'] == 5
    assert rows[0]['duration_seconds'] == 2700
    assert rows[0]['started_at']
    chats = client.get('/api/admin/chats').json['chats']
    assert next(room for room in chats if room['subject'] == 'math')['rating_count'] == 1


def test_updates_do_not_duplicate_and_new_appointments_do_not_overwrite(ratings):
    db, uid, client = ratings
    rate(client)
    rate(client, 4)
    assert db.appointment_ratings.count_documents({}) == 1
    assert db.appointment_ratings.find_one()['rating'] == 4
    assert client.post('/api/chat/appointment', json={
        "subject": "math", "appointment": "2026-10-02 10:00", "location": "Schule",
    }).status_code == 200
    assert client.get('/api/chat/appointment?subject=math').json['rating_count'] == 0
    assert db.appointment_ratings.count_documents({}) == 1
    assert client.post('/api/chat/appointment/start', json={"subject": "math"}).status_code == 200
    assert client.post('/api/chat/appointment/end', json={"subject": "math"}).status_code == 200
    rate(client, 5)
    assert sorted(r['rating'] for r in client.get('/api/admin/ratings').json['ratings']) == [4, 5]
    assert {r['appointment_snapshot']['location'] for r in db.appointment_ratings.find()} == {'Bibliothek', 'Schule'}


def test_legacy_ratings_are_archived_before_admin_clears_chat(ratings):
    db, uid, client = ratings
    db.chat_ratings.insert_one({"subject": "math", "user_id": uid, "rating": 3, "comment": "Alt", "created_at": app_module.utcnow()})
    app_module.delete_chat_subject_data(db, 'math')
    assert db.chat_ratings.count_documents({}) == 0
    assert db.appointment_ratings.find_one()['rating'] == 3
    assert client.get('/api/admin/ratings').json['ratings'][0]['duration_seconds'] == 2700
    app_module.delete_chat_subject_data(db)
    assert db.appointment_ratings.count_documents({}) == 1


def test_account_erasure_also_removes_archived_ratings(ratings):
    db, uid, client = ratings
    rate(client)
    app_module._erase_user_account(db, uid)
    assert db.appointment_ratings.count_documents({}) == 0
    assert db.chat_ratings.count_documents({}) == 0


def test_archive_keeps_admin_school_visibility(ratings):
    db, uid, client = ratings
    rate(client)
    with patch.object(app_module, '_has_full_read_access', return_value=False), \
         patch.object(app_module, 'admin_school', return_value='Other school'):
        assert client.get('/api/admin/ratings').json['ratings'] == []
