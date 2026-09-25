"""Persistent app cookies, browser isolation and logout, using an isolated DB."""
import unittest
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from unittest.mock import patch

import mongomock
from werkzeug.security import generate_password_hash
import app as app_module


APP_HEADERS = {"User-Agent": "Mozilla/5.0 Android BenConnectAndroid/1.0.2"}


class AndroidSessionTests(unittest.TestCase):
    def setUp(self):
        self.db = mongomock.MongoClient().test
        self.user_id = self.db.users.insert_one({
            "username": "session-test", "role": "user", "banned": 0,
            "password_hash": generate_password_hash("test-only-password"),
        }).inserted_id
        self.db_patch = patch.object(app_module, "get_db", return_value=self.db)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.client = app_module.app.test_client()

    def login(self, headers=APP_HEADERS, password="test-only-password"):
        return self.client.post("/login", data={
            "username": "session-test", "password": password,
        }, headers=headers)

    def cookie(self, response):
        cookies = SimpleCookie()
        for header in response.headers.getlist("Set-Cookie"):
            cookies.load(header)
        return cookies[app_module.app.config["SESSION_COOKIE_NAME"]]

    def test_app_login_is_persistent_and_survives_new_client(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        cookie = self.cookie(response)
        self.assertTrue(cookie["httponly"])
        expiry = self.client.get_cookie("session").expires
        self.assertAlmostEqual((expiry - datetime.now(timezone.utc)).total_seconds(),
                               timedelta(days=90).total_seconds(), delta=10)
        restarted = app_module.app.test_client()
        restarted.set_cookie("session", cookie.value)
        with restarted.get("/dashboard.html", headers=APP_HEADERS) as page:
            self.assertEqual(page.status_code, 200)

    def test_browser_login_remains_nonpersistent(self):
        response = self.login(headers={"User-Agent": "Mozilla/5.0"})
        self.assertEqual(self.cookie(response)["expires"], "")
        with self.client.session_transaction() as session:
            self.assertFalse(session.permanent)

    def test_existing_app_session_is_upgraded(self):
        self.login(headers={"User-Agent": "Mozilla/5.0"})
        response = self.client.get("/dashboard.html", headers=APP_HEADERS)
        self.addCleanup(response.close)
        self.assertTrue(self.cookie(response)["expires"])
        with self.client.session_transaction() as session:
            self.assertTrue(session.permanent)

    def test_activity_renews_expiration(self):
        self.login()
        old = self.client.get_cookie("session").expires
        import flask.sessions
        class Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(days=1)
        with patch.object(flask.sessions, "datetime", Later):
            response = self.client.get("/dashboard.html", headers=APP_HEADERS)
        self.addCleanup(response.close)
        self.assertTrue(self.cookie(response)["expires"])
        self.assertGreater(self.client.get_cookie("session").expires, old + timedelta(hours=23))

    def test_logout_deletes_persistent_cookie(self):
        self.login()
        response = self.client.post("/logout", headers=APP_HEADERS)
        self.assertEqual(self.cookie(response)["max-age"], "0")
        self.assertIsNone(self.client.get_cookie("session"))
        response = self.client.get("/dashboard.html", headers=APP_HEADERS)
        self.addCleanup(response.close)
        self.assertIn("/login.html", response.location)

    def test_failed_login_does_not_create_persistent_session(self):
        self.login(password="wrong")
        self.assertIsNone(self.client.get_cookie("session"))

    def test_anonymous_requests_do_not_create_cookies(self):
        response = self.client.get("/", headers=APP_HEADERS)
        self.addCleanup(response.close)
        self.assertFalse(response.headers.getlist("Set-Cookie"))

    def test_banned_user_session_is_cleared(self):
        self.login()
        self.db.users.update_one({"_id": self.user_id}, {"$set": {"banned": 1}})
        response = self.client.get("/dashboard.html", headers=APP_HEADERS)
        self.addCleanup(response.close)
        self.assertIn("banned", response.location)
        self.assertIsNone(self.client.get_cookie("session"))


if __name__ == "__main__":
    unittest.main()
