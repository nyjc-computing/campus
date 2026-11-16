"""HTTP contract tests for Campus token issuance on /token.

These tests drive the authorization-code exchange end to end (the
session's user_id and authorization_code are set the way the Google
leg's verify_login step sets them) and verify the scope algebra of
issuance per docs/auth-token-invariants.md:

- A3: an exchanged token covers every scope of its session; an
  existing covering grant is reused, never a narrower one.
- A4: re-authorization with new scopes unions into the existing grant
  (incremental scope authorization).
- A5: a superseded token record is deleted — the old access token
  stops authenticating immediately.
- RFC 6749 §4.1.3: only the client the code was issued to may
  exchange it.
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers

CALLBACK_URI = "https://issuance.example.com/finalize_login"
USER_ID = "issuer@nyjc.edu.sg"


class TestTokenIssuanceContract(unittest.TestCase):
    """HTTP contract tests for the /token scope algebra."""

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
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

    def _create_auth_code(
            self,
            scopes: list[str],
    ) -> str:
        """Create a session the way an app login would, up to the code.

        The app creates the session, the browser leg authenticates the
        user, and verify_login stamps user_id and the authorization
        code onto it. Here the stamping is done via the session PATCH
        endpoint, which accepts exactly those two fields.
        """
        response = self.client.post(
            "/auth/v1/sessions/campus/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": CALLBACK_URI,
                "scopes": scopes,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        session_id = response.get_json()["id"]

        code = f"test-code-{session_id}"
        response = self.client.patch(
            f"/auth/v1/sessions/campus/{session_id}/",
            json={"user_id": USER_ID, "authorization_code": code},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        return code

    def _exchange(self, code: str, client_id: str, client_secret: str):
        """Exchange an authorization code at POST /token."""
        return self.client.post(
            "/auth/v1/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CALLBACK_URI,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )

    def _bearer_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_exchange_issues_session_scopes(self):
        """A3: the token covers exactly the session's scopes."""
        code = self._create_auth_code(["read"])

        response = self._exchange(code, env.CLIENT_ID, env.CLIENT_SECRET)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["scope"], "read")
        # Minted tokens carry a refresh token for the refresh grant
        self.assertTrue(data["refresh_token"])

        # The token authenticates as a bearer credential. Management
        # routes deny user tokens outright (#854), so the probe is the
        # denial itself: 403 FORBIDDEN (authenticated but unauthorized),
        # never 401 (which would mean the token failed to resolve).
        listing = self.client.get(
            "/auth/v1/clients/",
            headers=self._bearer_headers(data["id"]),
        )
        self.assertEqual(listing.status_code, 403)
        self.assertEqual(listing.get_json()["error"]["code"], "FORBIDDEN")

    def test_wider_reauth_unions_scopes(self):
        """A3/A4: a wider re-authorization unions into the grant."""
        first_code = self._create_auth_code(["read"])
        first = self._exchange(first_code, env.CLIENT_ID, env.CLIENT_SECRET)
        self.assertEqual(first.status_code, 200)

        second_code = self._create_auth_code(["write"])
        second = self._exchange(second_code, env.CLIENT_ID, env.CLIENT_SECRET)

        self.assertEqual(second.status_code, 200)
        data = second.get_json()
        self.assertEqual(data["scope"], "read write")
        self.assertNotEqual(data["id"], first.get_json()["id"])

    def test_superseded_token_stops_authenticating(self):
        """A5: the pre-union token is dead once its record is superseded."""
        first_code = self._create_auth_code(["read"])
        first = self._exchange(first_code, env.CLIENT_ID, env.CLIENT_SECRET)
        first_token = first.get_json()["id"]

        second_code = self._create_auth_code(["write"])
        self._exchange(second_code, env.CLIENT_ID, env.CLIENT_SECRET)

        stale = self.client.get(
            "/auth/v1/clients/",
            headers=self._bearer_headers(first_token),
        )
        # The superseded credential no longer resolves, so the request
        # is rejected as 401 invalid_token (RFC 6750 §3.1, #729).
        self.assertEqual(stale.status_code, 401)

    def test_narrower_reauth_reuses_covering_token(self):
        """A3: a covering existing grant is reused, not re-issued."""
        first_code = self._create_auth_code(["read", "write"])
        first = self._exchange(first_code, env.CLIENT_ID, env.CLIENT_SECRET)
        self.assertEqual(first.get_json()["scope"], "read write")

        second_code = self._create_auth_code(["read"])
        second = self._exchange(second_code, env.CLIENT_ID, env.CLIENT_SECRET)

        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            second.get_json()["id"],
            first.get_json()["id"],
        )

    def test_code_exchange_by_wrong_client_rejected(self):
        """RFC 6749 §4.1.3: the code binds to the client it was issued to."""
        code = self._create_auth_code(["read"])

        # A second confidential client must not be able to exchange
        response = self.client.post(
            "/auth/v1/clients/",
            json={
                "name": "issuance-other-client",
                "description": "Second client for code-binding test",
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        other_id = response.get_json()["id"]
        secret_response = self.client.post(
            f"/auth/v1/clients/{other_id}/revoke",
            headers=self.auth_headers,
        )
        self.assertEqual(secret_response.status_code, 200)
        other_secret = secret_response.get_json()["secret"]

        response = self._exchange(code, other_id, other_secret)

        # RFC 6749 section 5.2: unauthorized_client is a 400 token error
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "AUTH_UNAUTHORIZED_CLIENT")
