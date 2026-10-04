"""Unit tests for the login `next` open-redirect validation.

flask_campus honors a caller-supplied `next` destination only when it
is a safe relative path. Protocol-relative URLs (//) were always
rejected; the backslash spelling (/\\) normalizes to // in browsers
and must be rejected too (#788) — matching the hardening the auth
service's logout endpoint already applies.
"""

import os
import unittest

import flask

from campus.flask_campus.login_manager import OAuthLoginManager


class _FakeAuth:
    """Minimal stand-in for campus_python's auth namespace."""

    def __init__(self):
        self.pushed = False

    def authorize(self, target):
        return flask.redirect(target)

    def push_context(self):
        self.pushed = True


class _FakeCampus:
    def __init__(self):
        self.auth = _FakeAuth()


class TestLoginNextValidation(unittest.TestCase):
    """GET /login?next=... stores the destination only when safe."""

    def setUp(self):
        # login stores the fallback via full_url_for, which resolves
        # PUBLIC_URL at call time; pin and restore around each test.
        self.saved = {
            name: os.environ.get(name)
            for name in ("ENV", "PUBLIC_URL")
        }
        os.environ["ENV"] = "testing"
        os.environ["PUBLIC_URL"] = "https://campus.test"
        self.app = flask.Flask(__name__)
        self.app.secret_key = "test-secret"

        @self.app.get("/")
        def index():
            return ""

        self.manager = OAuthLoginManager(
            campus_client=_FakeCampus()  # type: ignore[arg-type]
        )
        self.manager.init_app(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _stored_next(self) -> str:
        with self.client.session_transaction() as session:
            return session.get("login_next", "")

    def test_safe_next_is_preserved(self):
        response = self.client.get("/login?next=/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._stored_next(), "/dashboard")

    def test_protocol_relative_next_falls_back_to_default(self):
        self.client.get("/login?next=//evil.example.com")

        self.assertEqual(self._stored_next(), "https://campus.test/")

    def test_backslash_next_falls_back_to_default(self):
        r"""/\evil.example.com normalizes to //evil... in browsers."""
        self.client.get("/login?next=/\\evil.example.com")

        self.assertEqual(self._stored_next(), "https://campus.test/")


if __name__ == "__main__":
    unittest.main()
