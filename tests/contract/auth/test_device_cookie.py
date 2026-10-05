"""HTTP contract tests for the stable device cookie (#825).

These tests verify the device-identity contract of the login flow:

- GET /authorize sets a long-lived ``campus_device`` cookie on the
  auth origin, reused (not re-minted) on every later login from the
  same browser profile.
- The device id is recorded on the auth session and returned in the
  session resource, so the SDK can copy it onto the login session it
  creates — that login-session device_id is what spans carry.
- Each distinct browser profile (fresh cookie jar) gets its own
  device id.

The design lives in issue #825 and the narrative flow in
docs/auth-login-flow.md — keep all three in sync when changing the
flow.
"""

import unittest
from http import cookies as http_cookies

from campus.common import env
from campus.config import DEVICE_COOKIE
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

REGISTERED_URI = "https://app.example.com/finalize_login"


def _set_cookie_value(response, name: str) -> str | None:
    """Extract a Set-Cookie value for ``name`` from a response."""
    for header in response.headers.getlist("Set-Cookie"):
        jar = http_cookies.SimpleCookie()
        jar.load(header)
        if name in jar:
            return jar[name].value
    return None


def _set_cookie_morsel(response, name: str) -> http_cookies.Morsel | None:
    """Extract the full Set-Cookie morsel for ``name`` from a response."""
    for header in response.headers.getlist("Set-Cookie"):
        jar = http_cookies.SimpleCookie()
        jar.load(header)
        if name in jar:
            return jar[name]
    return None


class TestDeviceCookieContract(unittest.TestCase):
    """HTTP contract tests for the campus_device cookie (#825)."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()

        assert self.app
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    def _create_client(self) -> str:
        """Create an OAuth client and return its id."""
        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": "device-contract-client",
                "description": "Client for device cookie contract tests",
                "redirect_uris": [REGISTERED_URI],
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["id"]

    def _create_session(self, client_id: str) -> str:
        """Create an authorization session and return its ID."""
        response = self.client.post(
            "/auth/v1/sessions/campus/",
            json={
                "client_id": client_id,
                "redirect_uri": REGISTERED_URI,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["id"]

    def _authorize(self, client_id: str, session_id: str):
        """Issue an authorization request as a client app's browser would."""
        return self.client.get(
            "/auth/v1/authorize",
            query_string={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REGISTERED_URI,
                "state": session_id,
            },
        )

    def _session_resource(self, session_id: str) -> dict:
        response = self.client.get(
            f"/auth/v1/sessions/campus/{session_id}/",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def test_authorize_sets_device_cookie(self):
        """The first login mints a long-lived device cookie."""
        client_id = self._create_client()
        session_id = self._create_session(client_id)

        response = self._authorize(client_id, session_id)

        self.assertEqual(response.status_code, 302)
        device_id = _set_cookie_value(response, DEVICE_COOKIE)
        self.assertIsNotNone(device_id)
        self.assertTrue(device_id.startswith("uid-device-"))
        morsel = _set_cookie_morsel(response, DEVICE_COOKIE)
        assert morsel is not None
        # Device identity outlives sessions and logout: ~400 days
        # (Chrome's cap), HttpOnly, SameSite=Lax.
        self.assertGreater(int(morsel["max-age"]), 300 * 24 * 60 * 60)
        self.assertEqual(morsel["httponly"], True)
        self.assertEqual(morsel["samesite"], "Lax")

    def test_device_id_recorded_on_auth_session(self):
        """The session resource carries the device id from /authorize."""
        client_id = self._create_client()
        session_id = self._create_session(client_id)

        response = self._authorize(client_id, session_id)
        device_id = _set_cookie_value(response, DEVICE_COOKIE)
        assert device_id is not None

        resource = self._session_resource(session_id)
        self.assertEqual(resource["device_id"], device_id)

    def test_same_browser_reuses_device_id_across_logins(self):
        """A second login from the same browser keeps the device id.

        The test client persists its cookie jar between requests, so
        the second /authorize round-trip stands in for a re-login from
        the same browser profile days later.
        """
        client_id = self._create_client()

        first_session = self._create_session(client_id)
        first = self._authorize(client_id, first_session)
        first_device = _set_cookie_value(first, DEVICE_COOKIE)
        assert first_device is not None

        second_session = self._create_session(client_id)
        self._authorize(client_id, second_session)
        second_resource = self._session_resource(second_session)

        self.assertEqual(second_resource["device_id"], first_device)

    def test_fresh_browser_gets_fresh_device_id(self):
        """A new cookie jar (new browser profile) mints a new device."""
        client_id = self._create_client()

        first_session = self._create_session(client_id)
        first = self._authorize(client_id, first_session)
        first_device = _set_cookie_value(first, DEVICE_COOKIE)
        assert first_device is not None

        second_session = self._create_session(client_id)
        fresh_browser = self.app.test_client()
        second = fresh_browser.get(
            "/auth/v1/authorize",
            query_string={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": REGISTERED_URI,
                "state": second_session,
            },
        )
        second_device = _set_cookie_value(second, DEVICE_COOKIE)
        assert second_device is not None

        self.assertNotEqual(second_device, first_device)


if __name__ == "__main__":
    unittest.main()
