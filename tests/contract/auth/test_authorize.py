"""HTTP contract tests for the campus.auth /authorize endpoint.

These tests verify the redirect_uri validation contract required by
RFC 6749 §3.1.2.2 and §4.1.2.1 (#651, implemented fail-closed per #681):

- The request's redirect_uri must exactly match one of the client's
  registered redirect_uris.
- Clients with an empty redirect_uris list are rejected outright.
- The authorization session's redirect_uri must match the request's
  (the code is delivered to the session's redirect_uri).
- Rejections return 400 without redirecting to the supplied URI.

These tests are the executable specification of the authorization-code
flow's entry point. The endpoint-level schemas live in
campus/auth/docs/openapi.yaml (/auth/v1/authorize,
/auth/v1/sessions/{provider}/, /auth/v1/token) and the narrative flow
in docs/auth-login-flow.md — keep all three in sync when changing the
flow.
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

REGISTERED_URI = "https://app.example.com/finalize_login"
OTHER_URI = "https://other.example.com/finalize_login"
ATTACKER_URI = "https://attacker.example.com/callback"


class TestAuthorizeRedirectUriContract(unittest.TestCase):
    """HTTP contract tests for redirect_uri validation on /authorize."""

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

        assert self.app
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

    def _create_client(self, redirect_uris: list[str]) -> str:
        """Create a client with the given registered redirect_uris."""
        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": "authorize-contract-client",
                "description": "Client for /authorize contract tests",
                "redirect_uris": redirect_uris,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["redirect_uris"], redirect_uris)
        return data["id"]

    def _create_session(self, client_id: str, redirect_uri: str) -> str:
        """Create an authorization session and return its ID."""
        response = self.client.post(
            "/auth/v1/sessions/campus/",
            json={
                "client_id": client_id,
                "redirect_uri": redirect_uri,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        return data["id"]

    def _get_authorize(self, client_id: str, redirect_uri: str, state: str):
        """Issue an authorization request as a client app's browser would."""
        return self.client.get(
            "/auth/v1/authorize",
            query_string={
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "state": state,
            },
        )

    def test_registered_redirect_uri_redirects_to_google(self):
        """Exact-match registered redirect_uri proceeds to the Google flow."""
        client_id = self._create_client([REGISTERED_URI])
        session_id = self._create_session(client_id, REGISTERED_URI)

        response = self._get_authorize(client_id, REGISTERED_URI, session_id)

        self.assertEqual(response.status_code, 302)
        location = response.headers.get("Location", "")
        self.assertIn("/auth/v1/google/authorize", location)
        self.assertNotIn(ATTACKER_URI, location)

    def test_unregistered_redirect_uri_rejected_without_redirect(self):
        """An unregistered redirect_uri returns 400 without redirecting.

        RFC 6749 §4.1.2.1: the authorization server must inform the user
        of the error and MUST NOT redirect to the supplied URI.
        """
        client_id = self._create_client([REGISTERED_URI])
        session_id = self._create_session(client_id, REGISTERED_URI)

        response = self._get_authorize(client_id, ATTACKER_URI, session_id)

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Location", response.headers)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_REQUEST")

    def test_client_without_redirect_uris_rejected(self):
        """Clients with an empty redirect_uris list fail closed."""
        client_id = self._create_client([])
        session_id = self._create_session(client_id, REGISTERED_URI)

        response = self._get_authorize(client_id, REGISTERED_URI, session_id)

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Location", response.headers)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_REQUEST")

    def test_session_redirect_uri_mismatch_rejected(self):
        """A session whose redirect_uri is not the registered one fails.

        The authorization code is delivered to the session's redirect_uri,
        so a session created with a different (unregistered) URI must not
        pass validation even when the request presents a registered one.
        """
        client_id = self._create_client([REGISTERED_URI])
        session_id = self._create_session(client_id, OTHER_URI)

        response = self._get_authorize(client_id, REGISTERED_URI, session_id)

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Location", response.headers)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_REQUEST")
