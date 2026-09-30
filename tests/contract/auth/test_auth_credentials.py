"""HTTP contract tests for campus.auth credentials endpoints.

These tests verify the HTTP interface contract for credentials operations.
They test status codes, response formats, and authentication behavior.

Credentials Endpoints Reference:
- GET    /credentials/{provider}/            - List credentials or get by token_id
- GET    /credentials/{provider}/{user_id}   - Get credentials for user
- POST   /credentials/{provider}/{user_id}   - Create new credentials
- PATCH  /credentials/{provider}/{user_id}   - Update credentials
- DELETE /credentials/{provider}/{user_id}   - Delete credentials
"""

import unittest

import campus.model
from campus.common import env, schema
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_basic_auth_headers, get_bearer_auth_headers


class TestAuthCredentialsContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/credentials/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

        # Create a test user with bearer token
        cls.test_user_id = schema.UserID("contract.test@campus.test")
        cls.bearer_token = create_test_token(cls.test_user_id)

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        # Use the default test client for Basic Auth
        self.basic_auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)
        # Bearer auth headers for our test user
        self.bearer_auth_headers = get_bearer_auth_headers(self.bearer_token)

    def test_list_credentials_requires_auth(self):
        """GET /credentials/{provider}/ without auth returns 401."""
        response = self.client.get("/auth/v1/credentials/campus/")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_list_credentials_with_auth(self):
        """GET /credentials/{provider}/ returns list of credentials."""
        response = self.client.get(
            "/auth/v1/credentials/campus/",
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("credentials", data)
        self.assertIsInstance(data["credentials"], list)

    def test_get_credentials_by_token_id(self):
        """GET /credentials/{provider}/?token_id=X returns specific credentials."""
        response = self.client.get(
            f"/auth/v1/credentials/campus/?token_id={self.bearer_token}",
            headers=self.basic_auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # Credentials resource is returned directly (unwrapped)
        self.assertIn("id", data)
        self.assertIn("provider", data)

    def test_get_credentials_by_user_id(self):
        """GET /credentials/{provider}/{user_id} returns user credentials."""
        response = self.client.get(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # Credentials resource is returned directly (unwrapped)
        self.assertIn("id", data)
        self.assertIn("provider", data)
        self.assertIn("user_id", data)

    def test_get_credentials_missing_user_returns_404(self):
        """GET /credentials/{provider}/nonexistent returns 404."""
        response = self.client.get(
            "/auth/v1/credentials/campus/nonexistent@campus.test",
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 404)

    def test_create_credentials(self):
        """POST /credentials/{provider}/{user_id} creates new credentials."""
        new_user_id = schema.UserID("new.user@campus.test")

        response = self.client.post(
            f"/auth/v1/credentials/campus/{new_user_id}",
            json={
                "scopes": ["read", "write"],
                "expires_in": 3600
            },
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        # POST returns the token resource directly
        self.assertIn("id", data)
        self.assertIn("scope", data)

    def test_create_credentials_missing_fields_returns_422(self):
        """POST /credentials/{provider}/{user_id} without required fields returns 422.

        Missing request fields raise the structured ValidationError
        (422 VALIDATION_FAILED) from unpack_into, per the error-handling
        convention introduced by #347.
        """
        response = self.client.post(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            json={},  # Missing scopes and expires_in
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_update_credentials(self):
        """PATCH /credentials/{provider}/{user_id} updates credentials."""

        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            json={
                "token": {
                    "id": self.bearer_token,
                    "scopes": ["read", "write", "admin"],
                    "expires_in": 7200
                }
            },
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_create_credentials_expiry_seconds_returns_422(self):
        """POST with the removed expiry_seconds key returns 422 (#648
        item 2: the deprecation window closed; only expires_in is
        accepted)."""
        response = self.client.post(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            json={
                "scopes": ["read"],
                "expiry_seconds": 3600
            },
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_create_credentials_missing_expiry_returns_422(self):
        """POST without expires_in/expiry_seconds returns 422."""
        response = self.client.post(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            json={"scopes": ["read"]},
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")

    def test_update_credentials_accepts_resource_emission(self):
        """PATCH accepts a token resource as emitted by OAuthToken.to_resource().

        Regression test for #655: since #650 the token resource carries
        the RFC 6749 `scope` string alongside `scopes`; validating the
        PATCH body with OAuthToken(**token) rejected the model's own
        output with 422 VALIDATION_FAILED.
        """
        token = campus.model.OAuthToken(
            id=self.bearer_token,
            expires_in=7200,
            scopes=["read", "write", "admin"],
        )

        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            json={"token": token.to_resource()},
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_update_credentials_scope_only_token(self):
        """PATCH accepts a token carrying only the RFC 6749 `scope` string.

        When the #648 deprecation window closes, token resources will
        emit `scope` without the `scopes` alias; the validation path
        must already accept that shape (#655).
        """
        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            json={
                "token": {
                    "id": self.bearer_token,
                    "scope": "read write",
                    "expires_in": 7200,
                }
            },
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 200)

    def test_update_credentials_invalid_token_returns_422(self):
        """PATCH /credentials/{provider}/{user_id} with an invalid token
        object returns 422, not 500.

        Regression test for #325: a malformed token payload used to
        surface as an unhandled error (500).
        """
        response = self.client.patch(
            f"/auth/v1/credentials/campus/{self.test_user_id}",
            json={"token": {}},  # No expires_at or expiry_seconds
            headers=self.bearer_auth_headers
        )

        self.assertEqual(response.status_code, 422)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "VALIDATION_FAILED")
        fields = {e["field"] for e in data["error"]["errors"]}
        self.assertIn("token", fields)

    def test_delete_credentials(self):
        """DELETE /credentials/{provider}/{user_id} deletes credentials."""
        # Create a temporary user with credentials
        from tests.fixtures.tokens import create_test_token
        temp_user_id = schema.UserID("temp.user@campus.test")
        temp_token = create_test_token(temp_user_id)
        temp_headers = get_bearer_auth_headers(temp_token)

        # Delete the credentials
        response = self.client.delete(
            f"/auth/v1/credentials/campus/{temp_user_id}",
            json={},
            headers=temp_headers
        )

        self.assertEqual(response.status_code, 200)

        # Verify they're gone
        get_response = self.client.get(
            f"/auth/v1/credentials/campus/{temp_user_id}",
            headers=temp_headers
        )
        self.assertEqual(get_response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
