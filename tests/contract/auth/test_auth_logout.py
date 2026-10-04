"""HTTP contract tests for the campus.auth browser-session logout.

GET /auth/v1/logout clears the auth service's Flask session (the
campusauth SSO cookie established by identity login) and redirects to
a validated target (#785). It is unauthenticated: the session IS the
credential being cleared, so there is nothing to authenticate against.

Logout Endpoint Reference:
- GET /auth/v1/logout?post_logout_redirect_uri=/path
  - 302 to the target when it is a safe same-origin path
  - 302 to "/" on absent, cross-origin or unsafe targets
  - clears all session keys and expires the session cookie
"""

import unittest

from tests.fixtures import services


class TestAuthLogoutContract(unittest.TestCase):
    """HTTP contract tests for GET /auth/v1/logout."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()
        self.client = self.app.test_client()

    def _seed_session(self):
        """Give the test client a live-looking campusauth session."""
        with self.client.session_transaction() as session:
            session['user_id'] = 'logout.test@example.com'
            session['campus_session_id'] = 'campus-login_session_test'

    def test_logout_clears_session_and_redirects_to_target(self):
        """GET /logout with a safe same-origin target redirects there."""
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri=/goodbye"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/goodbye")
        with self.client.session_transaction() as session:
            self.assertEqual(dict(session), {})

    def test_logout_expires_session_cookie(self):
        """GET /logout sets an expired session cookie."""
        self._seed_session()
        response = self.client.get("/auth/v1/logout")

        set_cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("Expires=Thu, 01 Jan 1970", set_cookie)

    def test_logout_defaults_to_root_on_missing_target(self):
        """GET /logout without a target redirects to "/"."""
        self._seed_session()
        response = self.client.get("/auth/v1/logout")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_rejects_cross_origin_target(self):
        """Absolute URLs are never redirected to (open redirect)."""
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout"
            "?post_logout_redirect_uri=https://evil.example.com/phish"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_rejects_protocol_relative_target(self):
        """Protocol-relative URLs (//) are rejected."""
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri=//evil.example.com"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_rejects_backslash_target(self):
        r"""/\evil.example.com normalizes to //evil... in browsers."""
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri=/\\evil.example.com"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_without_session_is_idempotent(self):
        """GET /logout with no session still redirects cleanly."""
        response = self.client.get("/auth/v1/logout")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")


if __name__ == "__main__":
    unittest.main()
