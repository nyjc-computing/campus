"""Unit tests for finalize_login's handling of rejected codes.

The auth service rejects authorization codes as invalid for routine
reasons in a browser flow — a replayed single-use code (refresh,
back-button), or a code that expired on the consent screen. The
callback must send the user back to sign-in rather than serve an
unhandled 500 (#690).
"""

import unittest

import campus_python
import flask

from campus.flask_campus.login_manager import OAuthLoginManager


class _FakeAuth:
    """Minimal stand-in for campus_python's auth namespace."""

    def __init__(self, finalize_error: Exception | None = None):
        self.finalize_error = finalize_error
        self.finalized = False
        self.pushed = False

    def finalize(self, state, code, scope):
        if self.finalize_error is not None:
            raise self.finalize_error
        self.finalized = True

    def push_context(self):
        self.pushed = True


class _FakeCampus:
    def __init__(self, finalize_error: Exception | None = None):
        self.auth = _FakeAuth(finalize_error)


class TestFinalizeLoginRejection(unittest.TestCase):
    """A rejected authorization code redirects to sign-in, not a 500."""

    def _make_app(self, finalize_error: Exception | None):
        app = flask.Flask(__name__)
        app.secret_key = "test-secret"
        manager = OAuthLoginManager(
            campus_client=_FakeCampus(finalize_error)  # type: ignore[arg-type]
        )
        manager.init_app(app)
        return app, manager

    def test_rejected_code_redirects_to_sign_in(self):
        err = campus_python.errors.BadRequestError("Invalid authorization code")
        app, manager = self._make_app(err)
        client = app.test_client()
        response = client.get("/finalize_login?code=x&state=y&scope=z")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        with client.session_transaction() as session:
            flashes = [msg for _, msg in session.get("_flashes", [])]
        self.assertTrue(
            any("sign in again" in msg for msg in flashes),
            f"expected a sign-in flash message, got {flashes}"
        )

    def test_valid_code_completes_and_redirects(self):
        app, manager = self._make_app(None)
        client = app.test_client()
        response = client.get("/finalize_login?code=x&state=y&scope=z")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(manager.campus.auth.finalized)
        self.assertTrue(manager.campus.auth.pushed)


if __name__ == "__main__":
    unittest.main()
