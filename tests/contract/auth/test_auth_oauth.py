"""HTTP contract tests for campus.auth OAuth token endpoint.

These tests verify the HTTP interface contract for the OAuth token
endpoint (RFC 6749 grants over the device flow, plus the refresh_token
grant introduced by #678).

Token Endpoint Reference:
- POST /oauth/token  - Exchange an authorization grant for tokens

Contract invariants:
- Accepts application/x-www-form-urlencoded (OAuth 2.0 requirement)
  and JSON.
- Errors use the Campus error envelope with the OAuth error code in
  error.details.oauth_error (for API consistency).
- refresh_token grant issues a rotated token pair bound to the same
  client and scopes; the presented refresh token is single-use.
"""

import unittest

from tests.fixtures import services


class TestAuthOAuthTokenContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/oauth/token."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()

    def _token_request(self, body: dict):
        """POST the token endpoint with form encoding (OAuth 2.0 standard)."""
        return self.client.post(
            "/auth/v1/oauth/token",
            data=body,
            content_type="application/x-www-form-urlencoded"
        )

    def _complete_device_flow(self) -> dict:
        """Run a full device flow and return the token response data."""
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )
        create_data = create_response.get_json()

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'contract.test@campus.test'

            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={
                    "user_code": create_data["user_code"],
                    "user_id": "contract.test@campus.test",
                }
            )
            self.assertEqual(authorize_response.status_code, 200)

        token_response = self._token_request({
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": create_data["device_code"],
            "client_id": "guest",
        })
        self.assertEqual(token_response.status_code, 200)
        return token_response.get_json()

    def test_refresh_token_grant_returns_standard_token_response(self):
        """refresh_token grant returns the RFC 6749 token response shape."""
        original = self._complete_device_flow()

        response = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": original["refresh_token"],
            "client_id": "guest",
        })

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("access_token", data)
        self.assertIn("token_type", data)
        self.assertIn("expires_in", data)
        self.assertIn("refresh_token", data)
        self.assertIn("scope", data)
        self.assertEqual(data["token_type"], "Bearer")
        # Rotation is part of the contract: both values change
        self.assertNotEqual(data["access_token"], original["access_token"])
        self.assertNotEqual(data["refresh_token"], original["refresh_token"])

    def test_refresh_token_is_single_use(self):
        """A rotated-out refresh token is rejected on replay (invalid_grant)."""
        original = self._complete_device_flow()

        first = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": original["refresh_token"],
            "client_id": "guest",
        })
        self.assertEqual(first.status_code, 200)

        replay = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": original["refresh_token"],
            "client_id": "guest",
        })
        self.assertEqual(replay.status_code, 400)
        error = replay.get_json()["error"]
        self.assertEqual(error["details"]["oauth_error"], "invalid_grant")

    def test_refresh_token_bound_to_client(self):
        """A refresh token presented by a different client is rejected."""
        original = self._complete_device_flow()

        from campus.auth.resources import client as client_resource
        client_resource.new(
            id="otheroauthclient",
            name="Other OAuth Client",
            description="Contract test client for token binding",
            is_public=True,
            redirect_uris=["urn:ietf:wg:oauth:2.0:oob"],
        )

        response = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": original["refresh_token"],
            "client_id": "otheroauthclient",
        })
        self.assertEqual(response.status_code, 400)
        error = response.get_json()["error"]
        self.assertEqual(error["details"]["oauth_error"], "invalid_grant")

    def test_unknown_refresh_token_returns_invalid_grant(self):
        """Unknown refresh token returns 400 with invalid_grant."""
        response = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": "not-a-real-refresh-token",
            "client_id": "guest",
        })
        self.assertEqual(response.status_code, 400)
        error = response.get_json()["error"]
        self.assertEqual(error["details"]["oauth_error"], "invalid_grant")

    def test_missing_refresh_token_returns_invalid_request(self):
        """refresh_token grant without a token value returns invalid_request."""
        response = self._token_request({
            "grant_type": "refresh_token",
            "client_id": "guest",
        })
        self.assertEqual(response.status_code, 400)
        error = response.get_json()["error"]
        self.assertEqual(error["details"]["oauth_error"], "invalid_request")

    def test_unknown_grant_type_returns_unsupported_grant_type(self):
        """An unimplemented grant_type returns unsupported_grant_type."""
        response = self._token_request({
            "grant_type": "password",
            "client_id": "guest",
        })
        self.assertEqual(response.status_code, 400)
        error = response.get_json()["error"]
        self.assertEqual(
            error["details"]["oauth_error"], "unsupported_grant_type"
        )


if __name__ == '__main__':
    unittest.main()
