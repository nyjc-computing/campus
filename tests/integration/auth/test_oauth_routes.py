"""Integration tests for campus.auth OAuth routes.

Tests that the OAuth 2.0 Device Authorization Flow endpoints work correctly
with both JSON and form-encoded requests per RFC 8628.
"""

import unittest

from tests.fixtures import services


class TestOAuthIntegration(unittest.TestCase):
    """Integration tests for the OAuth routes in campus.auth."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()

        # Get the auth app from the service manager
        # OAuth routes are registered on the auth app, not the apps (API) app
        import flask
        auth_app = cls.service_manager.auth_app
        if not isinstance(auth_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = auth_app

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()

        # Reset test storage to clear SQLite in-memory database
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        """Set up test environment before each test."""
        self.client = self.app.test_client()

        # Set up test context
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        """Clean up after each test."""
        self.app_context.pop()

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
        # Campus returns structured errors, check for authorization_pending in details
        self.assertIn("error", token_data)
        # The error code should indicate authorization is pending
        error_code = token_data.get("error", {}).get("code", "")
        self.assertIn("PENDING", error_code)

    def test_oauth_verification_page(self):
        """Test the device verification page redirects unauthenticated users to login."""
        response = self.client.get("/auth/v1/oauth/device")

        # Unauthenticated users should be redirected to Google OAuth login
        self.assertEqual(response.status_code, 302)
        # Redirect should go to Google OAuth authorize endpoint
        self.assertIn("google", response.location.lower())


if __name__ == '__main__':
    unittest.main()
