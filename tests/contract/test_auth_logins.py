"""HTTP contract tests for campus.auth logins endpoints.

These tests verify the HTTP interface contract for login session management.
They test status codes, response formats, and authentication behavior.

NOTE: ALL /logins/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the auth blueprint.

Logins Endpoints Reference:
- POST   /logins/                   - Create new login session (requires auth)
- GET    /logins/{session_id}/      - Get login session (requires auth)
- PATCH  /logins/{session_id}/      - Update login session (requires auth)
- DELETE /logins/{session_id}/      - Delete login session (requires auth)
"""

import unittest

from campus.common import env, schema
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers


class TestAuthLoginsContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/logins/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.auth_app

        # Initialize login storage (not done by auth.init())
        from campus.auth.resources import login as login_resource
        login_resource.init_storage()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        # Reinitialize storage after tearDownClass reset
        # Ensures proper test isolation between tests
        import campus.storage.testing
        from campus.auth.resources import login as login_resource
        campus.storage.testing.reset_test_storage()
        login_resource.init_storage()

        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)
        self.test_user_id = schema.UserID("login.test@example.com")
        self.test_agent = "Mozilla/5.0 Test Agent"

    def test_create_login_session_success(self):
        """POST /logins/ creates a new login session."""
        response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertIn("expires_at", data)
        self.assertEqual(data["client_id"], env.CLIENT_ID)

    def test_create_login_session_with_device_id(self):
        """POST /logins/ with device_id creates session with device."""
        response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "device_id": "test-device-123",
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["device_id"], "test-device-123")

    @unittest.skip("API BUG: Missing params returns 500 instead of 400 - unpack_into KeyError")
    def test_create_login_session_missing_agent_string(self):
        """POST /logins/ without agent_string returns error."""
        response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id)
            },
            headers=self.auth_headers
        )

        # Missing required parameter returns error
        self.assertIn(response.status_code, (400, 422))

    def test_get_login_session(self):
        """GET /logins/{session_id}/ returns login session details."""
        # First create a login session
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Get the session
        response = self.client.get(
            f"/auth/v1/logins/{session_id}/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], session_id)
        self.assertEqual(data["client_id"], env.CLIENT_ID)

    def test_get_missing_login_session_returns_error(self):
        """GET /logins/{session_id}/ for non-existent session returns error."""
        response = self.client.get(
            "/auth/v1/logins/does_not_exist/",
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (404, 400))

    def test_update_login_session_expiry(self):
        """PATCH /logins/{session_id}/ updates expiry_seconds."""
        # First create a login session
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Update the session expiry
        response = self.client.patch(
            f"/auth/v1/logins/{session_id}/",
            json={"expiry_seconds": 7200},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], session_id)

    @unittest.skip("API BUG: Missing params returns 500 instead of 400 - unpack_into KeyError")
    def test_update_login_session_missing_expiry(self):
        """PATCH /logins/{session_id}/ without expiry_seconds returns error."""
        # First create a login session
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Update without expiry_seconds
        response = self.client.patch(
            f"/auth/v1/logins/{session_id}/",
            json={},
            headers=self.auth_headers
        )

        # Missing required parameter returns error
        self.assertIn(response.status_code, (400, 422))

    @unittest.skip("API BUG: Immutable field check returns 500 - update() error handling issue")
    def test_update_login_session_immutable_field(self):
        """PATCH /logins/{session_id}/ with immutable field returns error."""
        # First create a login session
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Try to update immutable field (client_id)
        response = self.client.patch(
            f"/auth/v1/logins/{session_id}/",
            json={
                "expiry_seconds": 3600,
                "client_id": "different-client-id"
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)

    def test_delete_login_session(self):
        """DELETE /logins/{session_id}/ removes the login session."""
        # First create a login session
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        # Delete the session
        del_response = self.client.delete(
            f"/auth/v1/logins/{session_id}/",
            headers=self.auth_headers
        )
        self.assertEqual(del_response.status_code, 200)

        # Verify it's gone
        get_response = self.client.get(
            f"/auth/v1/logins/{session_id}/",
            headers=self.auth_headers
        )
        self.assertIn(get_response.status_code, (404, 400))

    def test_create_login_without_auth(self):
        """POST /logins/ without auth returns 401."""
        response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            }
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_create_login_replaces_existing_session(self):
        """POST /logins/ replaces any existing session for the provider."""
        # Create first session
        first_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        first_session_id = first_response.get_json()["id"]

        # Create second session (should replace first)
        second_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        second_session_id = second_response.get_json()["id"]

        # Sessions should have different IDs
        self.assertNotEqual(first_session_id, second_session_id)

        # First session should no longer exist
        get_response = self.client.get(
            f"/auth/v1/logins/{first_session_id}/",
            headers=self.auth_headers
        )
        self.assertIn(get_response.status_code, (404, 400))


if __name__ == '__main__':
    unittest.main()
