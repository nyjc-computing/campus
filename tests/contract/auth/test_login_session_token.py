"""HTTP contract tests for login-session token re-acquisition (#963).

POST /auth/v1/logins/{session_id}/token is the session-bound
re-acquisition lane (invariant A10, docs/auth-token-invariants.md):
the session-owning confidential client re-acquires the user's campus
bearer without the operator-gated credentials routes (#854) and
without re-running the browser login. The matrix verified here:

- the owning client gets the live token (reuse), with no refresh
  token in the response;
- an expired token is rotated server-side with the same scopes, and
  supersession is deletion (A5);
- a missing credential record (revoked, C5) is invalid_grant, never
  minted from nothing;
- unknown and expired login sessions are invalid_grant;
- user principals, the operator, and non-owning clients are denied.

Fixtures follow test_management_authorization.py: the default test
client (env.CLIENT_ID) is the deployment operator; a second
"limited" confidential client plays the session-owning app.
"""

import unittest
import uuid

from campus.common import env, schema
from tests.fixtures import services
from tests.fixtures.tokens import (
    create_test_client_credentials,
    get_basic_auth_headers,
)

TEST_USER = "session-token.user@campus.test"


class TestLoginSessionToken(unittest.TestCase):
    """Authorization and issuance contract for POST /logins/{id}/token."""

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
        self.client = self.app.test_client()
        self.operator_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    # --- fixtures -------------------------------------------------

    def _create_user(self, user_id: str) -> None:
        from campus.auth.resources.user import user_storage

        user_storage.insert_one({
            "id": user_id,
            "created_at": "2024-01-01T00:00:00+00:00",
            "email": user_id,
            "name": "Session Token User",
            "activated_at": None,
        })

    def _create_limited_client(self) -> "tuple[str, str]":
        """Create a non-operator confidential client; returns (id, secret)."""
        return create_test_client_credentials(
            name=f"session-token-app-{uuid.uuid4().hex[:8]}",
            description="Session-owning app for #963 tests",
        )

    def _create_login(self, client_id: str, user_id: str) -> str:
        resp = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": client_id,
                "user_id": user_id,
                "agent_string": "Mozilla/5.0 Test Agent",
            },
            headers=self.operator_headers,
        )
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["id"]

    def _issue_credential(
            self,
            client_id: str,
            user_id: str,
            expires_in: int = 3600,
    ) -> str:
        """Create a campus credential for (user, client); returns token id."""
        from campus.auth import resources as auth_resources

        token = auth_resources.credentials["campus"][user_id].new(
            client_id=client_id,
            scopes=["read", "write"],
            expires_in=expires_in,
        )
        return token.id

    def _post_token(self, session_id: str, headers: dict):
        return self.client.post(
            f"/auth/v1/logins/{session_id}/token",
            headers=headers,
        )

    def assert_invalid_grant(self, response) -> dict:
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertEqual(data["error"]["details"]["oauth_error"], "invalid_grant")
        return data

    # --- the owning-client happy paths -----------------------------

    def test_owning_client_reacquires_live_token(self):
        """The owning client gets the live grant token; no refresh token."""
        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, limited_secret = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)
        token_id = self._issue_credential(limited_id, user_id)

        resp = self._post_token(
            login_id, get_basic_auth_headers(limited_id, limited_secret)
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        # A3 reuse: the live grant token is returned as-is.
        self.assertEqual(data["access_token"], token_id)
        self.assertEqual(data["token_type"], "Bearer")
        self.assertEqual(data["scope"], "read write")
        self.assertEqual(data["user_id"], user_id)
        self.assertGreater(data["expires_in"], 0)
        # B2 philosophy: campus refresh material never leaves this lane.
        self.assertNotIn("refresh_token", data)

    def test_expired_token_is_rotated_with_same_scopes(self):
        """An expired grant rotates server-side; supersession is deletion."""
        from campus.auth.resources.credentials import token_storage

        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, limited_secret = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)
        old_token_id = self._issue_credential(
            limited_id, user_id, expires_in=-3600
        )

        resp = self._post_token(
            login_id, get_basic_auth_headers(limited_id, limited_secret)
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertNotEqual(data["access_token"], old_token_id)
        self.assertEqual(data["scope"], "read write")
        self.assertNotIn("refresh_token", data)
        # A5: the superseded token record is deleted, so the old bearer
        # stops authenticating.
        self.assertIsNone(token_storage.get_by_id(old_token_id))
        self.assertIsNotNone(
            token_storage.get_by_id(data["access_token"])
        )

    def test_second_call_reuses_rotated_token(self):
        """A second re-acquisition returns the same (still-live) token."""
        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, limited_secret = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)
        self._issue_credential(limited_id, user_id)
        headers = get_basic_auth_headers(limited_id, limited_secret)

        first = self._post_token(login_id, headers)
        second = self._post_token(login_id, headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.get_json()["access_token"],
            second.get_json()["access_token"],
        )

    # --- invalid grants ---------------------------------------------

    def test_missing_credential_is_invalid_grant(self):
        """No campus grant for the user-client pair: invalid_grant, never
        minted from nothing (C5/A5 — revocation must force re-login)."""
        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, limited_secret = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)

        resp = self._post_token(
            login_id, get_basic_auth_headers(limited_id, limited_secret)
        )
        self.assert_invalid_grant(resp)

    def test_revoked_credential_is_invalid_grant(self):
        """A revoked token (deleted record) stays revoked under a live
        session: invalid_grant, not a fresh mint (C5)."""
        from campus.auth import resources as auth_resources

        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, limited_secret = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)
        self._issue_credential(limited_id, user_id)
        auth_resources.credentials["campus"][user_id].delete(limited_id)

        resp = self._post_token(
            login_id, get_basic_auth_headers(limited_id, limited_secret)
        )
        self.assert_invalid_grant(resp)

    def test_unknown_session_is_invalid_grant(self):
        """An unknown session id is invalid_grant."""
        limited_id, limited_secret = self._create_limited_client()
        resp = self._post_token(
            "no-such-login-session",
            get_basic_auth_headers(limited_id, limited_secret),
        )
        self.assert_invalid_grant(resp)

    def test_expired_login_session_is_invalid_grant(self):
        """An expired login session no longer authorizes issuance."""
        from campus.auth.resources.login import login_storage

        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, limited_secret = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)
        self._issue_credential(limited_id, user_id)
        expired_at = schema.DateTime.utcafter(
            schema.DateTime.utcnow(), seconds=-60
        )
        login_storage.update_by_id(login_id, {"expires_at": str(expired_at)})

        resp = self._post_token(
            login_id, get_basic_auth_headers(limited_id, limited_secret)
        )
        self.assert_invalid_grant(resp)

    # --- denied principals -------------------------------------------

    def test_foreign_client_denied(self):
        """A non-owning confidential client is denied (403)."""
        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, _ = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)
        self._issue_credential(limited_id, user_id)
        other_id, other_secret = self._create_limited_client()

        resp = self._post_token(
            login_id, get_basic_auth_headers(other_id, other_secret)
        )

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"]["code"], "FORBIDDEN")

    def test_operator_denied_even_on_own_session(self):
        """The operator is denied outright: the credentials management
        routes are its path (#854); this route stays laser-scoped."""
        user_id = TEST_USER
        self._create_user(user_id)
        login_id = self._create_login(env.CLIENT_ID, user_id)
        self._issue_credential(env.CLIENT_ID, user_id)

        resp = self._post_token(login_id, self.operator_headers)

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"]["code"], "FORBIDDEN")

    def test_operator_denied_on_foreign_session(self):
        """The operator is denied on another client's session too."""
        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, _ = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)
        self._issue_credential(limited_id, user_id)

        resp = self._post_token(login_id, self.operator_headers)

        self.assertEqual(resp.status_code, 403)

    def test_user_bearer_denied(self):
        """User principals are denied outright (#854): a user bearer is
        never the session's client, even when the minting client matches."""
        from tests.fixtures.tokens import create_test_token

        user_id = TEST_USER
        self._create_user(user_id)
        login_id = self._create_login(env.CLIENT_ID, user_id)
        self._issue_credential(env.CLIENT_ID, user_id)
        bearer = create_test_token(user_id, scopes=["read"])

        resp = self._post_token(
            login_id, {"Authorization": f"Bearer {bearer}"}
        )

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.get_json()["error"]["code"], "FORBIDDEN")

    def test_unauthenticated_request_denied(self):
        """No credentials at all: the Authenticator rejects with 401."""
        user_id = TEST_USER
        self._create_user(user_id)
        limited_id, _ = self._create_limited_client()
        login_id = self._create_login(limited_id, user_id)

        resp = self._post_token(login_id, {})

        self.assertEqual(resp.status_code, 401)


if __name__ == '__main__':
    unittest.main()
