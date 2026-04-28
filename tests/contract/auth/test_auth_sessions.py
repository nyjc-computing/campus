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
        from campus.common import schema

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
        """POST /sessions/{provider}/authorization_code with invalid code returns error."""
        response = self.client.post(
            f"/auth/v1/sessions/{self.test_provider}/authorization_code",  # Note: no trailing slash based on route definition
            json={"code": "invalid_auth_code_12345"},
            headers=self.auth_headers
        )

        # Invalid auth code should return an error (AccessDeniedError -> 401/403)
        # or 302 redirect if trailing slash is missing
        self.assertIn(response.status_code, (302, 401, 403))


if __name__ == '__main__':
    unittest.main()
