"""HTTP contract tests for the campus.auth browser-session logout.

GET /auth/v1/logout clears the auth service's Flask session (the
campusauth SSO cookie established by identity login) and redirects to
a validated target (#785). It is unauthenticated: the session IS the
credential being cleared, so there is nothing to authenticate against.

Logout Endpoint Reference:
- GET /auth/v1/logout?post_logout_redirect_uri=/path
  - 302 to the target when it is a safe same-origin path
  - 302 to the target when it is an absolute URL whose origin matches
    a registered client redirect_uri (#788)
  - 302 to "/" on absent, unregistered-origin or unsafe targets
  - clears all session keys and expires the session cookie
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

# The test harness resolves every service to the canonical origin
# (services fixture sets PUBLIC_URL), so a client registered with a
# redirect_uri on that origin exercises the registered-origin allowlist.
REGISTERED_ORIGIN = "https://campus.test"


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
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    def _seed_session(self):
        """Give the test client a live-looking campusauth session."""
        with self.client.session_transaction() as session:
            session['user_id'] = 'logout.test@example.com'
            session['campus_session_id'] = 'campus-login_session_test'

    def _register_client_redirect_uri(self) -> None:
        """Register a client whose redirect_uri origin is the harness origin."""
        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": "logout-allowlist-client",
                "description": "post_logout_redirect_uri allowlist source",
                "redirect_uris": [f"{REGISTERED_ORIGIN}/finalize_login"],
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)

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

    def test_logout_honors_registered_client_origin(self):
        """Absolute URL on a registered redirect_uri origin is honored.

        Path is free within the registered origin: sign-out can land
        on any page of the calling app (#788).
        """
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri="
            f"{REGISTERED_ORIGIN}/goodbye"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            f"{REGISTERED_ORIGIN}/goodbye"
        )

    def test_logout_honors_exact_registered_redirect_uri(self):
        """The registered redirect_uri itself is a valid target."""
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri="
            f"{REGISTERED_ORIGIN}/finalize_login"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            f"{REGISTERED_ORIGIN}/finalize_login"
        )

    def test_logout_rejects_unregistered_origin(self):
        """Absolute URLs on origins with no registered client are rejected."""
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout"
            "?post_logout_redirect_uri=https://stranger.example.com/x"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_rejects_scheme_mismatch(self):
        """http:// does not match a registered https:// origin."""
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri="
            f"http://{REGISTERED_ORIGIN.removeprefix('https://')}/goodbye"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_rejects_userinfo_authority(self):
        """Userinfo in the authority fails closed even on a registered host."""
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri="
            f"https://evil.example.com@{REGISTERED_ORIGIN.removeprefix('https://')}/"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_cross_site_initiator_drops_target(self):
        """Sec-Fetch-Site: cross-site signs out but lands on "/" (#797)."""
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri=/goodbye",
            headers={"Sec-Fetch-Site": "cross-site"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_cross_site_initiator_drops_registered_target(self):
        """Cross-site gets no redirect even to a registered origin."""
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri="
            f"{REGISTERED_ORIGIN}/goodbye",
            headers={"Sec-Fetch-Site": "cross-site"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_logout_same_site_initiator_keeps_target(self):
        """First-party hops arrive as same-site and keep the landing."""
        self._register_client_redirect_uri()
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri="
            f"{REGISTERED_ORIGIN}/goodbye",
            headers={"Sec-Fetch-Site": "same-site"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Location"],
            f"{REGISTERED_ORIGIN}/goodbye"
        )

    def test_logout_missing_sec_fetch_site_keeps_target(self):
        """No Sec-Fetch-Site header (older browsers, curl) is allowed."""
        self._seed_session()
        response = self.client.get(
            "/auth/v1/logout?post_logout_redirect_uri=/goodbye"
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/goodbye")


if __name__ == "__main__":
    unittest.main()
