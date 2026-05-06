"""Integration tests for campus.auth OAuth routes.

Tests that the OAuth 2.0 Device Authorization Flow endpoints work correctly
with both JSON and form-encoded requests per RFC 8628.
"""

import unittest
from unittest import mock

from tests.integration.base import IntegrationTestCase


class TestOAuthIntegration(IntegrationTestCase):
    """Integration tests for the OAuth routes in campus.auth."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        super().setUpClass()

        # Get the auth app from the service manager
        # OAuth routes are registered on the auth app, not the apps (API) app
        import flask
        auth_app = cls.service_manager.auth_app
        if not isinstance(auth_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = auth_app

    def test_oauth_device_authorize_with_json(self):
        """Test device authorization endpoint with JSON request."""
        response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            json={"client_id": "guest"},
            content_type="application/json"
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)

        # Verify response is valid JSON
        response_data = response.get_json()
        self.assertIsNotNone(response_data)

        # Check required fields per RFC 8628
        self.assertIn("device_code", response_data)
        self.assertIn("user_code", response_data)
        self.assertIn("verification_uri", response_data)
        self.assertIn("verification_uri_complete", response_data)
        self.assertIn("expires_in", response_data)
        self.assertIn("interval", response_data)

        # Verify all values are strings or integers (not bytes)
        self.assertIsInstance(response_data["device_code"], str)
        self.assertIsInstance(response_data["user_code"], str)
        self.assertIsInstance(response_data["verification_uri"], str)
        self.assertIsInstance(response_data["verification_uri_complete"], str)
        self.assertIsInstance(response_data["expires_in"], int)
        self.assertIsInstance(response_data["interval"], int)

        # Verify user_code format (XXXX-XXXX)
        self.assertRegex(response_data["user_code"], r"^[A-Z0-9]{4}-[A-Z0-9]{4}$")

    def test_oauth_device_authorize_with_form_data(self):
        """Test device authorization endpoint with form-encoded request.

        OAuth 2.0 spec requires accepting application/x-www-form-urlencoded.
        This test verifies the endpoint handles form data correctly.
        """
        response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)

        # Verify response is valid JSON
        response_data = response.get_json()
        self.assertIsNotNone(response_data)

        # Check required fields per RFC 8628
        self.assertIn("device_code", response_data)
        self.assertIn("user_code", response_data)
        self.assertIn("verification_uri", response_data)
        self.assertIn("verification_uri_complete", response_data)
        self.assertIn("expires_in", response_data)
        self.assertIn("interval", response_data)

        # Verify all values are strings or integers (not bytes)
        self.assertIsInstance(response_data["device_code"], str)
        self.assertIsInstance(response_data["user_code"], str)
        self.assertIsInstance(response_data["verification_uri"], str)
        self.assertIsInstance(response_data["verification_uri_complete"], str)
        self.assertIsInstance(response_data["expires_in"], int)
        self.assertIsInstance(response_data["interval"], int)

        # Verify user_code format (XXXX-XXXX)
        self.assertRegex(response_data["user_code"], r"^[A-Z0-9]{4}-[A-Z0-9]{4}$")

    def test_oauth_token_pending_with_form_data(self):
        """Test token endpoint with pending device code (form data).

        This verifies the polling mechanism returns authorization_pending
        when the user hasn't completed auth yet.
        """
        # First, create a device code
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )
        create_data = create_response.get_json()
        device_code = create_data["device_code"]

        # Then try to exchange it for a token (should be pending)
        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )

        self.assertEqual(token_response.status_code, 400)
        token_data = token_response.get_json()
        # OAuth errors use Campus envelope format (for API consistency)
        self.assertIn("error", token_data)
        error_obj = token_data.get("error", {})
        # Check Campus error code contains PENDING
        self.assertIn("PENDING", error_obj.get("code", ""))
        # Also verify the OAuth error in details
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "authorization_pending")

    def test_oauth_verification_page(self):
        """Test the device verification page redirects unauthenticated users to login."""
        response = self.client.get("/auth/v1/oauth/device")

        # Unauthenticated users should be redirected to Google OAuth login
        self.assertEqual(response.status_code, 302)
        # Redirect should go to Google OAuth authorize endpoint
        self.assertIn("google", response.location.lower())

    def test_device_verification_requires_authentication(self):
        """Test that device verification endpoint requires authentication."""
        # Without session - should redirect to login
        response = self.client.get("/auth/v1/oauth/device")
        self.assertEqual(response.status_code, 302)
        self.assertIn("google", response.location.lower())

        # With session - should show form
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'test@example.com'

            response = client.get("/auth/v1/oauth/device")
            self.assertEqual(response.status_code, 200)
            # Should contain the device verification form
            self.assertIn("Enter User Code", response.get_data(as_text=True))

    def test_user_query_parameter_ignored(self):
        """Test that user query parameter is ignored (security fix)."""
        # Try to access with user query parameter (old insecure method)
        response = self.client.get("/auth/v1/oauth/device?user=attacker@example.com")

        # Should still redirect to login, not trust the query param
        self.assertEqual(response.status_code, 302)
        self.assertIn("google", response.location.lower())

        # Session should NOT be set
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                self.assertNotIn('user_id', sess)

    def test_device_code_state_transitions(self):
        """Test device code state transitions: pending -> authorized -> consumed."""
        # 1. Create device code (state: pending)
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )
        create_data = create_response.get_json()
        device_code = create_data["device_code"]
        user_code = create_data["user_code"]

        # 2. Poll while pending -> returns authorization_pending
        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(token_response.status_code, 400)
        # OAuth errors use Campus envelope format (for API consistency)
        error_data = token_response.get_json()
        error_obj = error_data.get("error", {})
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "authorization_pending")

        # 3. Authorize the device code (state: authorized)
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'test@example.com'

            # Get the user to authorize
            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={"user_code": user_code, "user_id": "test@example.com"}
            )
            self.assertEqual(authorize_response.status_code, 200)

        # 4. Poll again -> returns token (state: consumed)
        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(token_response.status_code, 200)
        token_data = token_response.get_json()
        self.assertIn("access_token", token_data)

        # 5. Try to use same device code again -> error (already consumed)
        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(token_response.status_code, 400)
        # OAuth errors use Campus envelope format (for API consistency)
        error_data = token_response.get_json()
        error_obj = error_data.get("error", {})
        # Check for INVALID in Campus error code
        self.assertIn("INVALID", error_obj.get("code", ""))
        # Also verify the OAuth error in details
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "invalid_grant")

    def test_device_code_invalid(self):
        """Test that invalid device codes are rejected."""
        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": "invalid_device_code_12345",
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(token_response.status_code, 400)
        error_data = token_response.get_json()
        self.assertIn("error", error_data)
        # Check for INVALID in Campus error code
        error_obj = error_data.get("error", {})
        self.assertIn("INVALID", error_obj.get("code", ""))

    def test_device_code_expired(self):
        """Test that expired device codes are rejected.

        NOTE: This test uses time mocking which is unusual in this codebase.
        Mocking is necessary here because device codes have a time-based expiry
        (default 600 seconds) and we need to test the expiry behavior without
        waiting 10 minutes. Alternative would be to manually insert an expired
        device code into the database, but that would be testing database
        internals rather than the OAuth flow behavior.
        """
        import campus.config
        from campus.common.utils import utc_time
        from datetime import timedelta

        expiry_seconds = campus.config.DEFAULT_DEVICE_CODE_EXPIRY_SECONDS

        # Create a device code in the "past" by mocking time during creation
        # The device code's expires_at will be set based on the mocked time
        past_time = utc_time.now() - timedelta(seconds=expiry_seconds + 1)

        with mock.patch('campus.common.utils.utc_time.now', return_value=past_time):
            # Create device code (will have expires_at in the past relative to real time)
            create_response = self.client.post(
                "/auth/v1/oauth/device_authorize",
                data={"client_id": "guest"},
                content_type="application/x-www-form-urlencoded"
            )
            create_data = create_response.get_json()
            device_code = create_data["device_code"]

        # Now try to exchange the device code (without mock - real time is used)
        # Since the device code was created with a past time, it should be expired
        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(token_response.status_code, 400)
        # OAuth errors use Campus envelope format (for API consistency)
        error_data = token_response.get_json()
        self.assertIn("error", error_data)
        error_obj = error_data.get("error", {})
        # Check for EXPIRED in Campus error code
        self.assertIn("EXPIRED", error_obj.get("code", ""))
        # Also verify the OAuth error in details
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "expired_token")

    def test_device_code_already_used(self):
        """Test that already-used device codes are rejected."""
        # Create a device code
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )
        create_data = create_response.get_json()
        device_code = create_data["device_code"]
        user_code = create_data["user_code"]

        # Authorize it
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'test@example.com'

            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={"user_code": user_code, "user_id": "test@example.com"}
            )
            self.assertEqual(authorize_response.status_code, 200)

        # Get token
        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(token_response.status_code, 200)

        # Try to authorize again (should fail - already consumed/deleted)
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'test@example.com'

            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={"user_code": user_code, "user_id": "test@example.com"}
            )
            # Device code is deleted after token exchange, so we get 404
            self.assertEqual(authorize_response.status_code, 404)
            error_data = authorize_response.get_json()
            self.assertIn("error", error_data)

    def test_users_me_endpoint_returns_current_user_from_session(self):
        """Test that /oauth/users/me returns the current user from Flask session."""
        # Test without session - should return 401
        response = self.client.get("/auth/v1/oauth/users/me")
        self.assertEqual(response.status_code, 401)

        # Test with session - should return user data
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'test@example.com'

            response = client.get("/auth/v1/oauth/users/me")
            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn("user", data)
            self.assertEqual(data["user"]["id"], "test@example.com")


if __name__ == '__main__':
    unittest.main()
