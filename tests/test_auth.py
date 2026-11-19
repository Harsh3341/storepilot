from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from storepilot.auth import Auth, AuthError, hash_password
from storepilot.database import Database


PASSWORD = "correct horse store battery"


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.path = Path(self.directory.name) / "auth.sqlite3"
        self.database = Database(self.path)
        self.auth = Auth(self.database)

    def tearDown(self):
        self.database.close()
        self.directory.cleanup()

    def test_owner_hash_is_salted_and_plaintext_is_never_saved(self):
        self.assertFalse(self.auth.has_owner())
        self.auth.setup_owner("owner", PASSWORD)
        encoded = self.database.connection.execute("SELECT password_hash FROM auth_owner").fetchone()[0]
        self.assertNotIn(PASSWORD, encoded)
        self.assertEqual(encoded.split("$")[:2], ["pbkdf2_sha256", "600000"])
        self.assertNotEqual(hash_password(PASSWORD), hash_password(PASSWORD))
        with self.assertRaises(AuthError):
            self.auth.setup_owner("owner", "short")

    def test_login_saves_only_token_hash_and_session_survives_restart(self):
        self.auth.setup_owner("owner", PASSWORD)
        result = self.auth.login("owner", PASSWORD, "127.0.0.1")
        self.assertEqual(self.auth.session(result["token"])["username"], "owner")
        stored = self.database.connection.execute("SELECT token_hash,csrf_token FROM auth_sessions").fetchone()
        self.assertNotEqual(stored["token_hash"], result["token"])
        self.assertEqual(stored["csrf_token"], result["csrf_token"])
        self.database.close()
        self.database = Database(self.path)
        self.auth = Auth(self.database)
        self.assertEqual(self.auth.session(result["token"])["csrf_token"], result["csrf_token"])
        self.assertIsNone(self.auth.session("invalid-session-token"))

    def test_logout_and_password_reset_revoke_sessions(self):
        self.auth.setup_owner("owner", PASSWORD)
        first = self.auth.login("owner", PASSWORD, "127.0.0.1")
        self.auth.logout(first["token"])
        self.assertIsNone(self.auth.session(first["token"]))
        second = self.auth.login("owner", PASSWORD, "127.0.0.1")
        self.auth.setup_owner("owner", "replacement owner password")
        self.assertIsNone(self.auth.session(second["token"]))
        with self.assertRaises(AuthError) as error:
            self.auth.login("owner", PASSWORD, "127.0.0.1")
        self.assertEqual(error.exception.status_code, 401)

    def test_trusted_hash_provision_preserves_same_credentials_only(self):
        encoded = hash_password(PASSWORD)
        self.auth.setup_owner_hash("owner", encoded)
        session = self.auth.login("owner", PASSWORD, "127.0.0.1")
        self.auth.setup_owner_hash("owner", encoded)
        self.assertIsNotNone(self.auth.session(session["token"]))
        self.auth.setup_owner_hash("new-owner", encoded)
        self.assertIsNone(self.auth.session(session["token"]))
        for invalid in ("plaintext", encoded.replace("600000", "1"),
                        encoded.rsplit("$", 1)[0] + "$not-a-digest"):
            with self.subTest(invalid=invalid), self.assertRaises(AuthError):
                self.auth.setup_owner_hash("owner", invalid)

    def test_session_expires_after_seven_days(self):
        self.auth.setup_owner("owner", PASSWORD)
        start = datetime(2026, 11, 19, tzinfo=timezone.utc)
        with patch("storepilot.auth._now", return_value=start):
            result = self.auth.login("owner", PASSWORD, "127.0.0.1")
        with patch("storepilot.auth._now", return_value=start + timedelta(days=7)):
            self.assertIsNone(self.auth.session(result["token"]))

    def test_failed_attempt_rate_limit_persists_and_is_per_ip(self):
        self.auth.setup_owner("owner", PASSWORD)
        start = datetime(2026, 11, 19, tzinfo=timezone.utc)
        with patch("storepilot.auth._now", return_value=start):
            for _ in range(5):
                with self.assertRaises(AuthError) as error:
                    self.auth.login("owner", "wrong", "192.0.2.1")
                self.assertEqual(error.exception.status_code, 401)
            with self.assertRaises(AuthError) as error:
                Auth(self.database).login("owner", PASSWORD, "192.0.2.1")
            self.assertEqual(error.exception.status_code, 429)
            self.assertEqual(self.auth.login("owner", PASSWORD, "192.0.2.2")["username"], "owner")
        with patch("storepilot.auth._now", return_value=start + timedelta(minutes=16)):
            self.assertEqual(self.auth.login("owner", PASSWORD, "192.0.2.1")["username"], "owner")

    def test_login_without_provisioned_owner_is_conflict(self):
        with self.assertRaises(AuthError) as error:
            self.auth.login("owner", PASSWORD, "127.0.0.1")
        self.assertEqual(error.exception.status_code, 409)

    def test_invalid_unicode_credentials_fail_without_breaking_sessions(self):
        self.auth.setup_owner("owner", PASSWORD)
        for username, password in (("owner", "\ud800"), ("\ud800", PASSWORD)):
            with self.subTest(username_valid=username == "owner"), self.assertRaises(AuthError) as error:
                self.auth.login(username, password, "192.0.2.3")
            self.assertEqual(error.exception.status_code, 401)
        self.assertIsNone(self.auth.session("\ud800"))
