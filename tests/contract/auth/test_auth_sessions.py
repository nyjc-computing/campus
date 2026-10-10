"""HTTP contract tests for campus.auth sessions endpoints.

These tests verify the HTTP interface contract for session management operations.
They test status codes, response formats, and authentication behavior.

NOTE: ALL /sessions/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the auth blueprint.

Sessions Endpoints Reference:
- POST   /sessions/sweep                           - Sweep expired sessions (requires auth)
- POST   /sessions/{provider}/authorization_code   - Get session by auth code (requires auth)
- POST   /sessions/{provider}/                     - Create new provider session (requires auth)
- GET    /sessions/{provider}/{session_id}/        - Get session (requires auth)
- PATCH  /sessions/{provider}/{session_id}/        - Update session (requires auth)
- DELETE /sessions/{provider}/{session_id}/        - Finalize/delete session (requires auth)
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers


class TestAuthSessionsContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/sessions/ endpoints."""

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
        self.test_provider = "campus"
        self.test_redirect_uri = "https://example.com/callback"

    def test_sweep_sessions_requires_auth(self):
        """POST /sessions/sweep without auth returns 401."""
        response = self.client.post("/auth/v1/sessions/sweep")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])

    def test_sweep_sessions_with_auth(self):
        """POST /sessions/sweep with auth returns sweep count."""
        response = self.client.post(
            "/auth/v1/sessions/sweep",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("swept_count", data)
        self.assertIsInstance(data["swept_count"], int)

    def test_sweep_sessions_with_time(self):
        """POST /sessions/sweep with at_time parameter."""

        response = self.client.post(
            "/auth/v1/sessions/sweep",
            json={"at_time": None},  # None defaults to now
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("swept_count", data)

    def test_create_provider_session(self):
        """POST /sessions/{provider}/ creates a new auth session."""
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read", "write"]
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertIn("expires_at", data)
        self.assertEqual(data["provider"], self.test_provider)

    def test_create_provider_session_with_user_id(self):
        """POST /sessions/{provider}/ with user_id creates user-bound session."""
        from campus.common import schema

        user_id = schema.UserID("test.user@example.com")
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "user_id": str(user_id),
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["user_id"], str(user_id))

    def test_create_provider_session_missing_redirect_uri(self):
        """POST /sessions/{provider}/ without redirect_uri returns error."""
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )

        # Missing required parameter returns error
        self.assertIn(response.status_code, (400, 422))

    def test_get_provider_session(self):
        """GET /sessions/{provider}/{session_id}/ returns session details."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Get the session
        response = self.client.get(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], session_id)
        self.assertEqual(data["provider"], self.test_provider)

    def test_get_missing_session_returns_error(self):
        """GET /sessions/{provider}/{session_id}/ for non-existent session returns error."""
        response = self.client.get(
            f"/auth/v1/sessions/{self.test_provider}/does_not_exist/",
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (404, 400))

    def test_update_provider_session_user_id(self):
        """PATCH /sessions/{provider}/{session_id}/ updates user_id."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Update the session with user_id
        from campus.common import schema
        user_id = schema.UserID("updated.user@example.com")
        response = self.client.patch(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            json={"user_id": str(user_id)},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_update_provider_session_no_updates(self):
        """PATCH /sessions/{provider}/{session_id}/ without updates succeeds."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Update with empty body
        response = self.client.patch(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_delete_provider_session(self):
        """DELETE /sessions/{provider}/{session_id}/ finalizes the session."""
        # First create a session with a target
        target_uri = "https://example.com/target"
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"],
                "target": target_uri
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Finalize the session
        response = self.client.delete(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("target", data)
        self.assertEqual(data["target"], target_uri)

    def test_delete_provider_session_no_target(self):
        """DELETE /sessions/{provider}/{session_id}/ with no target returns null target."""
        # First create a session without a target
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Finalize the session
        response = self.client.delete(
            f"/auth/v1/sessions/{self.test_provider}/{session_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # Target may be None or not present
        self.assertIn("target", data)

    def test_get_session_by_authorization_code(self):
        """POST /sessions/{provider}/authorization_code retrieves session by code."""
        # First create a session
        create_response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/",
            json={
                "client_id": env.CLIENT_ID,
                "redirect_uri": self.test_redirect_uri,
                "scopes": ["read"]
            },
            headers=self.auth_headers
        )
        session_data = create_response.get_json()
        auth_code = session_data.get("authorization_code")

        # Get session by authorization code
        # Note: authorization_code endpoint has no trailing slash in route
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/authorization_code",
            json={"code": auth_code},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["id"], session_data["id"])

    def test_get_session_by_invalid_authorization_code(self):
        """POST /sessions/{provider}/authorization_code with invalid code returns 400."""
        response = self.client.post(
            # No trailing slash, per the route definition
            f"/auth/v1/sessions/{self.test_provider}/authorization_code",
            json={"code": "invalid_auth_code_12345"},
            headers=self.auth_headers
        )

        # A failed code exchange is a bad request, not an auth failure: the
        # caller is authenticated, the input code is invalid. RFC 6749 5.2
        # puts access_denied in the 400 token-error response, and the route
        # raises auth_errors.AccessDeniedError (status_code 400) for it (#623).
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)


class TestSessionUserEmbedding(unittest.TestCase):
    """Session reads and finalization embed the user record for the
    session-owning client or the operator (#879); other principals get
    no user data.

    flask_campus apps hydrate the signed-in user from these responses
    instead of the operator-gated GET /users/{id}.
    """

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
        self.provider = "campus"

    def _create_user(self, user_id: str) -> None:
        """Insert a user record directly (storage-level, as in the
        users contract tests)."""
        from contextlib import suppress

        from campus.auth.resources.user import user_storage

        with suppress(Exception):
            user_storage.delete_by_id(user_id)
        user_storage.insert_one({
            "id": user_id,
            "created_at": "2024-01-01T00:00:00+00:00",
            "email": user_id,
            "name": "Session User",
            "activated_at": None,
        })

    def _create_session(self, user_id: str | None = None) -> str:
        """Create a session owned by the main test client."""
        body = {
            "client_id": env.CLIENT_ID,
            "redirect_uri": "https://example.com/callback",
            "scopes": ["read"],
        }
        if user_id is not None:
            body["user_id"] = user_id
        resp = self.client.post(
            f"/auth/v1/sessions/{self.provider}/",
            json=body,
            headers=self.auth_headers,
        )
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["id"]

    def _create_other_client(self) -> "tuple[str, str]":
        """Create a fresh non-owner, non-operator client.

        Returns (client_id, client_secret); the secret is only ever
        revealed at rotation time, so this is the one chance to hold it.
        """
        resp = self.client.post(
            "/auth/v1/clients/",
            json={"name": "other-app", "description": "not the owner"},
            headers=self.auth_headers,
        )
        other_id = resp.get_json()["id"]
        resp = self.client.post(
            f"/auth/v1/clients/{other_id}/revoke",
            json={},
            headers=self.auth_headers,
        )
        assert resp.status_code == 200, resp.get_json()
        return other_id, resp.get_json()["secret"]

    def _other_client_headers(self, other_id: str, other_secret: str) -> dict:
        """Basic headers for the given non-owner client."""
        return get_basic_auth_headers(other_id, other_secret)

    def test_get_embeds_user_for_owning_client(self):
        """GET /sessions/{p}/{id}/ embeds the user for the owning client."""
        user_id = "session.user@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user"]["id"], user_id)
        self.assertEqual(data["user"]["email"], user_id)
        self.assertEqual(data["user"]["name"], "Session User")

    def test_get_omits_user_for_other_client(self):
        """GET /sessions/{p}/{id}/ omits the user for a non-owner client."""
        user_id = "session.user2@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)
        other_id, other_secret = self._create_other_client()

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self._other_client_headers(other_id, other_secret),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json().get("user"))

    def test_get_embeds_user_for_operator_of_foreign_session(self):
        """The operator sees the embedded user on another client's session."""
        other_id, other_secret = self._create_other_client()
        resp = self.client.post(
            f"/auth/v1/sessions/{self.provider}/",
            json={
                "client_id": other_id,
                "redirect_uri": "https://example.com/callback",
            },
            headers=self._other_client_headers(other_id, other_secret),
        )
        self.assertEqual(resp.status_code, 200)
        session_id = resp.get_json()["id"]
        user_id = "session.user3@example.com"
        self._create_user(user_id)
        # Bind the user to the session via PATCH (operator allowed).
        patch = self.client.patch(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            json={"user_id": user_id},
            headers=self.auth_headers,
        )
        self.assertEqual(patch.status_code, 200)

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["id"], user_id)

    def test_get_without_user_record_returns_null_user(self):
        """A missing user record degrades to a null embed, not a 500."""
        user_id = "ghost.user@example.com"
        session_id = self._create_session(user_id)

        response = self.client.get(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json().get("user"))

    def test_finalize_embeds_user_for_owning_client(self):
        """DELETE /sessions/{p}/{id}/ carries target and the user (#879)."""
        user_id = "session.finalize@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)

        response = self.client.delete(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("target", data)
        self.assertEqual(data["user"]["id"], user_id)

    def test_finalize_omits_user_for_other_client(self):
        """DELETE /sessions/{p}/{id}/ omits the user for a non-owner."""
        user_id = "session.finalize2@example.com"
        self._create_user(user_id)
        session_id = self._create_session(user_id)

        other_id, other_secret = self._create_other_client()
        response = self.client.delete(
            f"/auth/v1/sessions/{self.provider}/{session_id}/",
            headers=self._other_client_headers(other_id, other_secret),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json().get("user"))


if __name__ == '__main__':
    unittest.main()
