from unittest.mock import patch

import mongomock
import pytest

import app as app_module


@pytest.mark.parametrize('cleanup', ['leave', 'subject', 'all'])
def test_reports_survive_chat_cleanup_and_can_still_be_resolved(cleanup):
    db = mongomock.MongoClient(tz_aware=True).test
    reporter = db.users.insert_one({'username': 'Pro', 'role': 'dev', 'level_math': 'pro'}).inserted_id
    author = db.users.insert_one({'username': 'Author', 'role': 'user', 'school': 'School A', 'class_name': '8a'}).inserted_id
    db.chat_presence.insert_one({'subject': 'math', 'user_id': reporter, 'level': 'pro'})
    message = db.chat_messages.insert_one({'subject': 'math', 'user_id': author, 'username': 'Author', 'body': 'Gemeldeter Inhalt'}).inserted_id
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session.update(user_id=str(reporter), username='Pro', role='dev')
    with patch.object(app_module, 'get_db', return_value=db):
        response = client.post('/api/chat/report-message', json={'message_id': str(message), 'reason': 'Beleidigung'})
        assert response.status_code == 200
        report_id = db.chat_message_reports.find_one()['_id']
        if cleanup == 'leave':
            assert client.post('/api/chat/leave', json={'subject': 'math'}).status_code == 200
        else:
            assert client.post('/api/admin/chat-clear', json={'subject': 'math' if cleanup == 'subject' else ''}).status_code == 200
        assert db.chat_messages.count_documents({}) == 0
        reports = client.get('/api/admin/chat-reports').json['reports']
        assert len(reports) == 1
        assert reports[0]['body'] == 'Gemeldeter Inhalt'
        assert reports[0]['reason'] == 'Beleidigung'
        assert reports[0]['reported_username'] == 'Author'
        assert reports[0]['created_at']
        with patch.object(app_module, '_has_full_read_access', return_value=False), \
             patch.object(app_module, 'admin_school', return_value='School B'):
            assert client.get('/api/admin/chat-reports').json['reports'] == []
        response = client.post(f'/api/admin/chat-reports/{report_id}/resolve')
        assert response.status_code == 200
        assert client.get('/api/admin/chat-reports').json['reports'] == []
        assert db.chat_message_reports.find_one({'_id': report_id})['resolved_at']
        app_module.delete_chat_subject_data(db)
        assert db.chat_message_reports.count_documents({}) == 1
