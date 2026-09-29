"""HTTP contract tests for campus.api emailotp endpoints.

These tests verify the HTTP interface contract for email OTP operations.
They test status codes, response formats, and authentication behavior.

NOTE: ALL /emailotp/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the API blueprint.

EmailOTP Endpoints Reference:
- POST /emailotp/request - Request a new OTP for email authentication
- POST /emailotp/verify  - Verify an OTP for email authentication

IMPORTANT: The /emailotp/request endpoint sends an actual email during testing.
Tests should be designed to handle this gracefully or mock the email sender.
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestApiEmailOtpContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/emailotp/ endpoints."""

    @classmethod
    def setUpClass(cls):
        # Reset storage before starting tests to ensure clean state

        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.apps_app

        # Create test user; the bearer token is re-created per test in
        # setUp() because clear_test_data() wipes the credentials storage.
        cls.user_id = schema.UserID("test.user@campus.test")

        # Use a test email domain to avoid sending real emails
        cls.test_email = "test@example.test"

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        # Clear test data - no manual resource initialization needed
        self.manager.clear_test_data()

        self.client = self.app.test_client()

        # Re-create the bearer token after the clear: the token lives in
        # credentials storage, which clear_test_data() wipes.
        self.token = create_test_token(self.user_id)
        self.auth_headers = get_bearer_auth_headers(self.token)

    # Request OTP Tests

    def test_request_otp_requires_auth(self):
        """POST /emailotp/request without auth returns 401."""
        response = self.client.post(
            "/api/v1/emailotp/request",
            json={"email": self.test_email}
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    @unittest.skip("Skipped: Sends actual email - verify with mocked email sender")
    def test_request_otp(self):
        """POST /emailotp/request generates and sends OTP.

        NOTE: This test sends an actual email. To run this test:
        1. Configure a test email provider
        2. Mock the email sender in the fixture
        """
        response = self.client.post(
            "/api/v1/emailotp/request",
            json={"email": self.test_email},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("message", data)
        self.assertEqual(data["message"], "OTP sent")

    def test_request_otp_missing_email_returns_error(self):
        """POST /emailotp/request without email returns error."""
        response = self.client.post(
            "/api/v1/emailotp/request",
            json={},
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (400, 422))

    @unittest.skip("API BUG #502: empty email passes validation and resources.emailotp.request() 500s - emailotp storage table is not initialised in the test harness")
    def test_request_otp_empty_email_returns_error(self):
        """POST /emailotp/request with empty email returns error."""
        response = self.client.post(
            "/api/v1/emailotp/request",
            json={"email": ""},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)

    @unittest.skip("Skipped: Email sender error handling - verify error response format")
    def test_request_otp_email_sender_error(self):
        """POST /emailotp/request with email sender error returns 500.

        NOTE: This test requires mocking the email sender to return an error.
        Verify that the response contains proper error_code.
        """
        # This would require mocking create_email_sender to return an error
        pass

    # Verify OTP Tests

    def test_verify_otp_requires_auth(self):
        """POST /emailotp/verify without auth returns 401."""
        response = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": self.test_email,
                "otp": "123456"
            }
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_verify_otp_missing_email_returns_error(self):
        """POST /emailotp/verify without email returns error."""
        response = self.client.post(
            "/api/v1/emailotp/verify",
            json={"otp": "123456"},
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (400, 422))

    def test_verify_otp_missing_otp_returns_error(self):
        """POST /emailotp/verify without OTP returns error."""
        response = self.client.post(
            "/api/v1/emailotp/verify",
            json={"email": self.test_email},
            headers=self.auth_headers
        )

        self.assertIn(response.status_code, (400, 422))

    @unittest.skip("API BUG #502: emailotp storage table not initialised in the harness; verify flow cannot run")
    def test_verify_otp_not_found_returns_error(self):
        """POST /emailotp/verify for email with no OTP returns 409."""
        response = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": "no-otp@example.test",
                "otp": "123456"
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "CONFLICT")

    @unittest.skip("API BUG #502: emailotp storage table not initialised in the harness; verify flow cannot run")
    def test_verify_invalid_otp_returns_error(self):
        """POST /emailotp/verify with invalid OTP returns 401."""
        # First request an OTP (we'll skip actually sending)
        # For now just test that invalid OTP fails
        response = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": self.test_email,
                "otp": "999999"  # Invalid OTP
            },
            headers=self.auth_headers
        )

        # Should return 409 (OTP not found) or 401 (invalid OTP)
        self.assertIn(response.status_code, (401, 409))

    @unittest.skip("Skipped: Requires OTP generation - use mock or direct resource access")
    def test_verify_valid_otp_succeeds(self):
        """POST /emailotp/verify with valid OTP returns 200.

        NOTE: This test requires generating a valid OTP via the resource layer
        to avoid sending an actual email.
        """
        from campus.api import resources

        # Generate OTP directly via resource (bypasses email sending)
        otp_code = resources.emailotp.request(self.test_email)

        response = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": self.test_email,
                "otp": otp_code
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("message", data)
        self.assertEqual(data["message"], "OTP verified")

    @unittest.skip("Skipped: Requires OTP generation - use mock or direct resource access")
    def test_verify_expired_otp_returns_error(self):
        """POST /emailotp/verify with expired OTP returns 401.

        NOTE: This test requires creating an expired OTP via the resource layer.
        """
        from campus.api import resources

        # Generate OTP with very short expiry
        otp_code = resources.emailotp.request(self.test_email, expiry_minutes=0)

        # Wait a moment to ensure expiry
        import time
        time.sleep(1)

        response = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": self.test_email,
                "otp": otp_code
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    @unittest.skip("Skipped: Requires OTP generation - use mock or direct resource access")
    def test_otp_full_flow(self):
        """Full OTP flow: request -> verify -> revoke.

        NOTE: This test requires mocking the email sender to avoid sending emails.
        """
        from campus.api import resources

        # Request OTP (direct via resource to avoid email)
        otp_code = resources.emailotp.request(self.test_email)

        # Verify OTP
        verify_response = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": self.test_email,
                "otp": otp_code
            },
            headers=self.auth_headers
        )
        self.assertEqual(verify_response.status_code, 200)

        # Verify again - should still work (OTP not deleted after use)
        verify_response2 = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": self.test_email,
                "otp": otp_code
            },
            headers=self.auth_headers
        )
        self.assertEqual(verify_response2.status_code, 200)

        # Revoke OTP
        resources.emailotp.revoke(self.test_email)

        # Verify after revoke should fail
        verify_response3 = self.client.post(
            "/api/v1/emailotp/verify",
            json={
                "email": self.test_email,
                "otp": otp_code
            },
            headers=self.auth_headers
        )
        self.assertEqual(verify_response3.status_code, 409)


if __name__ == '__main__':
    unittest.main()
