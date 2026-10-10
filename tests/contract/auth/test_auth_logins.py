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
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()

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

        self.assertIn(response.status_code, (400, 422))

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

    def test_delete_login_session_by_owning_client_without_cookie(self):
        """DELETE /logins/{session_id}/ by the owning client needs no cookie.

        Server-to-server clients hold the auth-service session cookie in
        a per-process in-memory jar, so a second worker or a restarted
        process cannot present the cookie its own POST /logins
        established (#692). Revocation is allowed for the owning client:
        the request is already authenticated with that client's
        credentials, the same credentials that created the session.
        """
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

        # A fresh test client models the second worker / restarted
        # process: same Basic credentials, empty cookie jar.
        fresh_worker = self.app.test_client()
        del_response = fresh_worker.delete(
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

    def test_delete_foreign_login_session_without_cookie_returns_error(self):
        """DELETE /logins/{session_id}/ without cookie or ownership errors.

        The cookie-less revocation path is limited to sessions the
        authenticated client owns; a session recorded against another
        client_id stays unrevokable without the matching client-side
        session cookie.
        """
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": "foreign-client",
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent
            },
            headers=self.auth_headers
        )
        session_id = create_response.get_json()["id"]

        fresh_worker = self.app.test_client()
        del_response = fresh_worker.delete(
            f"/auth/v1/logins/{session_id}/",
            headers=self.auth_headers
        )
        self.assertIn(del_response.status_code, (404, 409))

    def _mint_bearer_token(self, user_id: str) -> str:
        """Run a device flow as user_id and return the access token."""
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded",
        )
        device_data = create_response.get_json()

        with self.app.test_client() as browser:
            with browser.session_transaction() as sess:
                sess["user_id"] = user_id
            authorize_response = browser.post(
                "/auth/v1/oauth/device/authorize",
                json={"user_code": device_data["user_code"], "user_id": user_id},
            )
            self.assertEqual(authorize_response.status_code, 200)

        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_data["device_code"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(token_response.status_code, 200)
        return token_response.get_json()["access_token"]

    def test_bearer_user_revokes_own_login_session(self):
        """DELETE /logins/{id}/ with Bearer works for the owning user (#837).

        Non-browser clients (the CLI) create their login session
        server-side and hold no auth-service cookie, so revocation must
        work on the presenting user's own bearer token alone.
        """
        device_user = "contract.test@campus.test"
        token = self._mint_bearer_token(device_user)
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": "guest",
                "user_id": device_user,
                "device_id": "uid-device-cli-test",
                "agent_string": "campus-cli/test",
            },
            headers=self.auth_headers,
        )
        session_id = create_response.get_json()["id"]

        # A fresh client models the CLI: bearer credentials only, no
        # cookie jar — the cookie-synced delete path cannot apply.
        fresh_client = self.app.test_client()
        del_response = fresh_client.delete(
            f"/auth/v1/logins/{session_id}/",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(del_response.status_code, 200)

        get_response = self.client.get(
            f"/auth/v1/logins/{session_id}/",
            headers=self.auth_headers,
        )
        self.assertIn(get_response.status_code, (404, 400))

    def test_bearer_user_cannot_revoke_foreign_login_session(self):
        """A bearer token may not revoke another user's login session."""
        token = self._mint_bearer_token("contract.test@campus.test")
        create_response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": str(self.test_user_id),
                "agent_string": self.test_agent,
            },
            headers=self.auth_headers,
        )
        session_id = create_response.get_json()["id"]

        # A fresh client models the CLI: bearer credentials only, no
        # cookie jar from a prior browser-style POST /logins.
        fresh_client = self.app.test_client()
        del_response = fresh_client.delete(
            f"/auth/v1/logins/{session_id}/",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Falls through to the cookie-synced path, which requires the
        # browser session: 404 without deleting the record.
        self.assertIn(del_response.status_code, (404, 409))

        get_response = self.client.get(
            f"/auth/v1/logins/{session_id}/",
            headers=self.auth_headers,
        )
        self.assertEqual(get_response.status_code, 200)

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


class TestLoginUserEmbedding(unittest.TestCase):
    """Login-session reads embed the user record for the session-owning
    client or the operator (#879); other principals get no user data.

    flask_campus push_context resolves the signed-in user from the
    login-session read instead of the operator-gated GET /users/{id}.
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
        self.manager.clear_test_data()

        assert self.app
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)
        self.test_agent = "Mozilla/5.0 Test Agent"

    def _create_user(self, user_id: str) -> None:
        from contextlib import suppress

        from campus.auth.resources.user import user_storage

        with suppress(Exception):
            user_storage.delete_by_id(user_id)
        user_storage.insert_one({
            "id": user_id,
            "created_at": "2024-01-01T00:00:00+00:00",
            "email": user_id,
            "name": "Login User",
            "activated_at": None,
        })

    def _create_login(self, user_id: str) -> str:
        resp = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": env.CLIENT_ID,
                "user_id": user_id,
                "agent_string": self.test_agent,
            },
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
        """GET /logins/{id}/ embeds the user for the owning client."""
        user_id = "login.user@example.com"
        self._create_user(user_id)
        login_id = self._create_login(user_id)

        response = self.client.get(
            f"/auth/v1/logins/{login_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["user"]["id"], user_id)
        self.assertEqual(data["user"]["email"], user_id)

    def test_get_omits_user_for_other_client(self):
        """GET /logins/{id}/ omits the user for a non-owner client."""
        user_id = "login.user2@example.com"
        self._create_user(user_id)
        login_id = self._create_login(user_id)
        other_id, other_secret = self._create_other_client()

        response = self.client.get(
            f"/auth/v1/logins/{login_id}/",
            headers=self._other_client_headers(other_id, other_secret),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json().get("user"))

    def test_get_without_user_record_returns_null_user(self):
        """A missing user record degrades to a null embed, not a 500."""
        user_id = "login.ghost@example.com"
        login_id = self._create_login(user_id)

        response = self.client.get(
            f"/auth/v1/logins/{login_id}/",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.get_json().get("user"))


if __name__ == '__main__':
    unittest.main()
