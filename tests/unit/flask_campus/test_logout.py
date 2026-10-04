"""Unit tests for flask_campus /logout routing through the auth service.

App-side sign-out must end the campusauth SSO session, not just
revoke the login_sessions record: the auth service holds its own
Flask session behind its cookie (#785). /logout therefore redirects
the browser through the auth service's browser-session logout
endpoint, superseding the app's own post-logout redirect.
"""

import os
import unittest

import flask

from campus.flask_campus.login_manager import OAuthLoginManager

_AUTH_LOGOUT_URL = "https://campus.test/auth/v1/logout"


class _FakeAuth:
    """Minimal stand-in for campus_python's auth namespace."""

    def __init__(self):
        self.logged_out = False
        self.pushed = False

    def logout(self):
        self.logged_out = True

    def push_context(self):
        self.pushed = True


class _FakeCampus:
    def __init__(self):
        self.auth = _FakeAuth()


class TestLogoutRoutesThroughAuthService(unittest.TestCase):
    """GET /logout revokes, then redirects to the auth service logout."""

    def setUp(self):
        # get_base_url resolves through ENV/PUBLIC_URL at call time;
        # pin both and restore around each test.
        self.saved = {
            name: os.environ.get(name)
            for name in ("ENV", "PUBLIC_URL")
        }
        os.environ["ENV"] = "testing"
        os.environ["PUBLIC_URL"] = "https://campus.test"
        self.app = flask.Flask(__name__)
        self.app.secret_key = "test-secret"
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

    def test_logout_revokes_then_redirects_to_auth_service(self):
        response = self.client.get("/logout")

        self.assertTrue(self.manager.campus.auth.logged_out)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], _AUTH_LOGOUT_URL)

    def test_logout_redirect_target_is_auth_logout_endpoint(self):
        """The browser is sent to /auth/v1/logout, not the app."""
        response = self.client.get("/logout")

        location = response.headers["Location"]
        self.assertTrue(
            location.endswith("/auth/v1/logout"),
            f"expected the auth service logout endpoint, got {location}"
        )


if __name__ == "__main__":
    unittest.main()
