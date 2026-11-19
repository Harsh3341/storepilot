from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from storepilot.auth import Auth
from storepilot.auth_api import make_auth_router
from storepilot.database import Database


class Settings:
    secure_cookies = False
    session_cookie = "storepilot_session"

    def accepts_origin(self, request):
        return request.headers.get("origin") in (None, "http://testserver")


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.database = Database(Path(self.directory.name) / "auth.sqlite3")
        self.auth = Auth(self.database)
        app = FastAPI()
        app.include_router(make_auth_router(self.auth, Settings()))
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.database.close()
        self.directory.cleanup()

    def provision(self):
        self.auth.setup_owner("owner", "correct horse store battery")

    def login(self, **options):
        return self.client.post("/api/auth/login", json={"username": "owner", "password": "correct horse store battery"}, **options)

    def test_unconfigured_status_and_login_conflict(self):
        self.assertEqual(self.client.get("/api/auth/session").json(),
                         {"enabled": False, "authenticated": False, "username": None, "csrf_token": None})
        self.assertEqual(self.login().status_code, 409)

    def test_login_uses_cookie_and_body_does_not_leak_token(self):
        self.provision()
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])
        self.assertNotIn("token", response.json())
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertIn("Max-Age=604800", cookie)
        self.assertIn("Path=/", cookie)
        self.assertNotIn("Secure", cookie)
        session = self.client.get("/api/auth/session")
        self.assertEqual(session.json()["csrf_token"], response.json()["csrf_token"])
        self.assertEqual(session.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_login_rejects_bad_origin_and_unexpected_or_nonstring_fields(self):
        self.provision()
        self.assertEqual(self.login(headers={"Origin": "https://attacker.example"}).status_code, 403)
        for body in ({"username": "owner", "password": 123},
                     {"username": "owner", "password": "wrong", "role": "admin"}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/auth/login", json=body).status_code, 422)
        self.assertEqual(self.client.post("/api/auth/login", data={"username": "owner", "password": "wrong"}).status_code, 422)

    def test_bad_password_is_generic_and_logout_revokes_cookie(self):
        self.provision()
        response = self.client.post("/api/auth/login", json={"username": "other", "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("owner", response.json()["detail"])
        self.login()
        token = self.client.cookies.get("storepilot_session")
        self.assertEqual(self.client.post("/api/auth/logout").json(), {"ok": True})
        self.assertIsNone(self.auth.session(token))
        self.assertFalse(self.client.get("/api/auth/session").json()["authenticated"])

    def test_production_cookie_is_secure(self):
        self.provision()
        settings = Settings()
        settings.secure_cookies = True
        app = FastAPI()
        app.include_router(make_auth_router(self.auth, settings))
        with TestClient(app, base_url="https://testserver") as client:
            response = client.post("/api/auth/login", json={"username": "owner", "password": "correct horse store battery"})
            self.assertIn("Secure", response.headers["set-cookie"])
            self.assertTrue(client.get("/api/auth/session").json()["authenticated"])
