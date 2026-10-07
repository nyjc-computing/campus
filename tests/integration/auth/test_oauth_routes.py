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

        # Verification URIs must be built from the canonical origin
        # (PUBLIC_URL, falling back to HOSTNAME), not the request host (#652)
        self.assertEqual(
            response_data["verification_uri"],
            "https://campus.test/auth/v1/oauth/device"
        )
        self.assertEqual(
            response_data["verification_uri_complete"],
            f"https://campus.test/auth/v1/oauth/device?user_code={response_data['user_code']}"
        )

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

        # Verification URIs must be built from the canonical origin
        # (PUBLIC_URL, falling back to HOSTNAME), not the request host (#652)
        self.assertEqual(
            response_data["verification_uri"],
            "https://campus.test/auth/v1/oauth/device"
        )
        self.assertEqual(
            response_data["verification_uri_complete"],
            f"https://campus.test/auth/v1/oauth/device?user_code={response_data['user_code']}"
        )

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

    def test_oauth_token_slow_down_on_fast_polls(self):
        """RFC 8628 §3.5: re-polls inside the interval get slow_down (#355).

        The first poll is free (clients may poll immediately after
        receiving the code); from the second poll on, the pending
        polling loop is throttled to the advertised interval.
        """
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )
        device_code = create_response.get_json()["device_code"]

        def _poll():
            return self.client.post(
                "/auth/v1/oauth/token",
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": "guest",
                },
                content_type="application/x-www-form-urlencoded"
            )

        # First pending poll: allowed, records last_polled_at
        first = _poll()
        self.assertEqual(first.status_code, 400)
        oauth_error = (
            first.get_json().get("error", {})
            .get("details", {}).get("oauth_error", "")
        )
        self.assertEqual(oauth_error, "authorization_pending")

        # Immediate re-poll: inside the interval -> slow_down
        second = _poll()
        self.assertEqual(second.status_code, 400)
        oauth_error = (
            second.get_json().get("error", {})
            .get("details", {}).get("oauth_error", "")
        )
        self.assertEqual(oauth_error, "slow_down")

        # After the interval passes, polling is allowed again
        from campus.auth.resources import device_code as device_code_resource
        from campus.common import schema

        dc = device_code_resource.get_by_device_code(device_code)
        device_code_resource.update(
            dc.id,
            last_polled_at=schema.DateTime.utcafter(
                schema.DateTime.utcnow(), seconds=-10
            ),
        )
        third = _poll()
        self.assertEqual(third.status_code, 400)
        oauth_error = (
            third.get_json().get("error", {})
            .get("details", {}).get("oauth_error", "")
        )
        self.assertEqual(oauth_error, "authorization_pending")

        # Regression (#847): a storage round-trip (Mongo/BSON) hands the
        # model a plain str, not schema.DateTime — the throttle must
        # still slow_down instead of 500ing on .to_datetime().
        dc = device_code_resource.get_by_device_code(device_code)
        device_code_resource.update(
            dc.id,
            last_polled_at=str(schema.DateTime.utcnow()),
        )
        fourth = _poll()
        self.assertEqual(fourth.status_code, 400)
        oauth_error = (
            fourth.get_json().get("error", {})
            .get("details", {}).get("oauth_error", "")
        )
        self.assertEqual(oauth_error, "slow_down")

    def test_oauth_token_poll_not_throttled_after_authorize(self):
        """Terminal polls are not throttled: authorized -> token (#355).

        The pending poll records last_polled_at, and the authorized
        poll lands well inside the interval; it must still return the
        token (the claim, not the throttle, serializes terminal polls).
        """
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )
        create_data = create_response.get_json()
        device_code = create_data["device_code"]
        user_code = create_data["user_code"]

        # Pending poll records the poll timestamp
        pending = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(pending.status_code, 400)

        # Authorize immediately (well inside the interval)
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'test@example.com'

            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={"user_code": user_code, "user_id": "test@example.com"}
            )
            self.assertEqual(authorize_response.status_code, 200)

        # The authorized poll must not be slow_downed
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
        self.assertIn("access_token", token_response.get_json())

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
        with self.app.test_client() as client, client.session_transaction() as sess:
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
        from datetime import timedelta

        import campus.config
        from campus.common.utils import utc_time

        expiry_seconds = campus.config.DEFAULT_DEVICE_CODE_EXPIRY_SECONDS

        # Create a device code in the "past" by mocking time during creation
        # The device code's expires_at will be set based on the mocked time.
        # The margin must exceed expiry_seconds by MORE than is_expired()'s
        # 1-second threshold: is_expired() requires (now - expires_at) > 1
        # strictly, so a margin of exactly +1 makes the verdict depend on the
        # clock advancing between this read and the server's check. When the
        # whole round trip lands inside one OS clock tick (~15ms on Windows),
        # (now - expires_at) is exactly 1.0 and the code reads as pending,
        # flaking this test.
        past_time = utc_time.now() - timedelta(seconds=expiry_seconds + 2)

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


    def _complete_device_flow(self) -> dict:
        """Run a full device flow as the test user and return the token response."""
        create_response = self.client.post(
            "/auth/v1/oauth/device_authorize",
            data={"client_id": "guest"},
            content_type="application/x-www-form-urlencoded"
        )
        create_data = create_response.get_json()

        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user_id'] = 'test@example.com'

            authorize_response = client.post(
                "/auth/v1/oauth/device/authorize",
                json={"user_code": create_data["user_code"],
                      "user_id": "test@example.com"}
            )
            self.assertEqual(authorize_response.status_code, 200)

        token_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": create_data["device_code"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(token_response.status_code, 200)
        return token_response.get_json()

    def test_refresh_token_grant_returns_rotated_pair(self):
        """Test that the refresh_token grant issues a rotated token pair."""
        original = self._complete_device_flow()
        self.assertIn("refresh_token", original)

        refresh_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": original["refresh_token"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(refresh_response.status_code, 200)
        refreshed = refresh_response.get_json()

        # Standard token response fields
        self.assertIn("access_token", refreshed)
        self.assertIn("refresh_token", refreshed)
        self.assertIn("token_type", refreshed)
        self.assertIn("expires_in", refreshed)
        self.assertIn("scope", refreshed)
        self.assertEqual(refreshed["token_type"], "Bearer")

        # Rotation: both values must differ from the originals
        self.assertNotEqual(refreshed["access_token"], original["access_token"])
        self.assertNotEqual(refreshed["refresh_token"], original["refresh_token"])

        # Scopes are preserved from the original grant
        self.assertEqual(refreshed["scope"], original["scope"])

    def test_refresh_token_replay_rejected_after_rotation(self):
        """Test that a rotated-out refresh token cannot be replayed.

        The credential update deletes the superseded token record, so
        the old refresh token must no longer resolve (#678).
        """
        original = self._complete_device_flow()

        first_refresh = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": original["refresh_token"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(first_refresh.status_code, 200)

        # Replay the original refresh token -> rejected
        replay_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": original["refresh_token"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(replay_response.status_code, 400)
        error_obj = replay_response.get_json().get("error", {})
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "invalid_grant")

    def test_refresh_token_wrong_client_rejected(self):
        """Test that a refresh token presented by a different client is rejected."""
        original = self._complete_device_flow()

        # Register a second public client to present the foreign token
        from campus.auth.resources import client as client_resource
        other = client_resource.new(
            id="otherclient",
            name="Other Refresh Client",
            description="Client that must not accept foreign refresh tokens",
            is_public=True,
            redirect_uris=["urn:ietf:wg:oauth:2.0:oob"],
        )
        self.assertEqual(other.id, "otherclient")

        refresh_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": original["refresh_token"],
                "client_id": "otherclient",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(refresh_response.status_code, 400)
        error_obj = refresh_response.get_json().get("error", {})
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "invalid_grant")

    def test_refresh_token_invalid_rejected(self):
        """Test that an unknown refresh token is rejected with invalid_grant."""
        refresh_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": "not-a-real-refresh-token",
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(refresh_response.status_code, 400)
        error_obj = refresh_response.get_json().get("error", {})
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "invalid_grant")

    def test_refresh_token_missing_rejected(self):
        """Test that a refresh_token grant without the token value is invalid_request."""
        refresh_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(refresh_response.status_code, 400)
        error_obj = refresh_response.get_json().get("error", {})
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "invalid_request")

    def _bearer_credentials_status(self, user_id: str, token: str) -> int:
        """Probe a bearer-authenticated endpoint with the given access token."""
        response = self.app.test_client().get(
            f"/auth/v1/credentials/campus/{user_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.status_code

    def test_revoke_access_token_invalidates_bearer_auth(self):
        """Test that revoking an access token invalidates bearer auth (#677).

        Bearer authentication resolves the credential record by token
        id, so revocation deletes the credential record; the token then
        authenticates like one that never existed (401, not 200) —
        RFC 6750 §3.1 invalid_token semantics (#729).
        """
        tokens = self._complete_device_flow()
        user_id = "test@example.com"

        self.assertEqual(
            self._bearer_credentials_status(user_id, tokens["access_token"]),
            200
        )

        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "token": tokens["access_token"],
                "token_type_hint": "access_token",
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 200)

        self.assertEqual(
            self._bearer_credentials_status(user_id, tokens["access_token"]),
            401
        )

    def test_revoke_refresh_token_also_invalidates_access_token(self):
        """Test RFC 7009 section 2.1: revoking a refresh token also
        invalidates the associated access token (one token record)."""
        tokens = self._complete_device_flow()
        user_id = "test@example.com"

        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "token": tokens["refresh_token"],
                "token_type_hint": "refresh_token",
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 200)

        # The refresh token no longer grants tokens
        refresh_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(refresh_response.status_code, 400)

        # The associated access token is dead too
        self.assertEqual(
            self._bearer_credentials_status(user_id, tokens["access_token"]),
            401
        )

    def test_revoke_without_hint_kills_pair(self):
        """Test that revoking with no token_type_hint kills the pair."""
        tokens = self._complete_device_flow()
        user_id = "test@example.com"

        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "token": tokens["access_token"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 200)

        self.assertEqual(
            self._bearer_credentials_status(user_id, tokens["access_token"]),
            401
        )
        refresh_response = self.client.post(
            "/auth/v1/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(refresh_response.status_code, 400)

    def test_revoke_wrong_client_does_not_revoke(self):
        """Test that a client cannot revoke another client's token.

        The response is still 200 (RFC 7009 section 2.2 — no validity
        disclosure) but the token must keep working.
        """
        tokens = self._complete_device_flow()
        user_id = "test@example.com"

        from campus.auth.resources import client as client_resource
        client_resource.new(
            id="otherrevokeclient",
            name="Other Revoke Client",
            description="Client that must not revoke foreign tokens",
            is_public=True,
            redirect_uris=["urn:ietf:wg:oauth:2.0:oob"],
        )

        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "token": tokens["access_token"],
                "client_id": "otherrevokeclient",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 200)

        # The token was NOT revoked
        self.assertEqual(
            self._bearer_credentials_status(user_id, tokens["access_token"]),
            200
        )

    def test_revoke_unknown_token_returns_200(self):
        """Test RFC 7009 section 2.2: unknown tokens still return 200."""
        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "token": "not-a-real-token",
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 200)

    def test_revoke_idempotent_returns_200(self):
        """Test RFC 7009 section 2.2: revoking twice returns 200 both times."""
        tokens = self._complete_device_flow()

        for _ in range(2):
            revoke_response = self.client.post(
                "/auth/v1/oauth/revoke",
                data={
                    "token": tokens["access_token"],
                    "client_id": "guest",
                },
                content_type="application/x-www-form-urlencoded"
            )
            self.assertEqual(revoke_response.status_code, 200)

    def test_revoke_missing_token_returns_400_invalid_request(self):
        """Test RFC 7009 section 2.1: a missing token is invalid_request."""
        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "client_id": "guest",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 400)
        error_obj = revoke_response.get_json().get("error", {})
        oauth_error = error_obj.get("details", {}).get("oauth_error", "")
        self.assertEqual(oauth_error, "invalid_request")


class TestClientCredentialsGrant(IntegrationTestCase):
    """Integration tests for the client_credentials grant (RFC 6749 4.4).

    campus#334 / campus-classroom#24: a confidential client exchanges
    its registered secret for an app-scoped token that authenticates
    the client with no user, enabling service-to-service Campus API
    reads (campus-python's with_app_session()).
    """

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        super().setUpClass()

        # The token endpoint lives on the auth app
        import flask
        auth_app = cls.service_manager.auth_app
        if not isinstance(auth_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = auth_app

    def _grant(self, **overrides):
        """POST a client_credentials token request (form-encoded).

        Defaults to the fixture's confidential test client (allowed
        scopes: read, write). A None override value removes the field,
        for missing-parameter cases.
        """
        from campus.common import env
        body = {
            "grant_type": "client_credentials",
            "client_id": env.get("CLIENT_ID"),
            "client_secret": env.get("CLIENT_SECRET"),
        }
        for key, value in overrides.items():
            if value is None:
                body.pop(key, None)
            else:
                body[key] = value
        return self.client.post(
            "/auth/v1/oauth/token",
            data=body,
            content_type="application/x-www-form-urlencoded"
        )

    def _grant_token(self, **overrides) -> str:
        """Run a successful grant and return the access token."""
        response = self._grant(**overrides)
        assert response.status_code == 200, response.get_json()
        return response.get_json()["access_token"]

    @staticmethod
    def _oauth_error(response) -> str:
        """Extract the RFC 6749 error code from an error envelope."""
        error_obj = response.get_json().get("error", {})
        return error_obj.get("details", {}).get("oauth_error", "")

    def test_grant_returns_app_token_without_refresh_token(self):
        """Test the happy path: standard token response, no refresh token."""
        response = self._grant()
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["token_type"], "Bearer")
        self.assertIn("access_token", data)
        # Fixture test-client allowlist is ["read", "write"]; an absent
        # scope parameter defaults to the full allowlist
        self.assertEqual(set(data["scope"].split()), {"read", "write"})
        # RFC 6749 section 4.4.3: no refresh token on this grant
        self.assertNotIn("refresh_token", data)

    def test_grant_accepts_json_body(self):
        """Test that the grant works with a JSON body (campus-python
        posts JSON to this endpoint)."""
        from campus.common import env
        response = self.client.post(
            "/auth/v1/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": env.get("CLIENT_ID"),
                "client_secret": env.get("CLIENT_SECRET"),
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.get_json())

    def test_grant_reports_remaining_lifetime(self):
        """Test that expires_in is bounded by the configured token
        lifetime (full lifetime on a fresh issue)."""
        import campus.config
        response = self._grant()
        data = response.get_json()
        max_lifetime = (
            campus.config.DEFAULT_TOKEN_EXPIRY_DAYS * 24 * 60 * 60
        )
        self.assertGreater(data["expires_in"], 0)
        self.assertLessEqual(data["expires_in"], max_lifetime)

    def test_grant_reuses_live_token(self):
        """Test that repeated grants with the same scopes reuse the
        client's live token instead of accumulating token records."""
        first = self._grant().get_json()
        second = self._grant().get_json()
        self.assertEqual(first["access_token"], second["access_token"])

    def test_grant_with_scope_param_narrows_and_supersedes(self):
        """Test the scope parameter narrows the grant, and a different
        scope set supersedes the live token (invariant A5: the replaced
        token record is deleted, a fresh one issued)."""
        narrowed = self._grant(scope="read")
        self.assertEqual(narrowed.status_code, 200)
        self.assertEqual(narrowed.get_json()["scope"], "read")

        full = self._grant()
        self.assertEqual(full.status_code, 200)
        self.assertNotEqual(
            narrowed.get_json()["access_token"],
            full.get_json()["access_token"]
        )

    def test_grant_scope_outside_allowlist_rejected(self):
        """Test invariant A1 (fail-closed allowlist): a scope outside
        the client's registered allowlist rejects the whole request."""
        response = self._grant(scope="read admin")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._oauth_error(response), "invalid_scope")

    def test_grant_invalid_secret_rejected(self):
        """Test that a wrong client secret is rejected with
        invalid_client (RFC 6749 section 5.2)."""
        response = self._grant(client_secret="wrong-secret")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self._oauth_error(response), "invalid_client")

    def test_grant_missing_secret_rejected(self):
        """Test that omitting client_secret is invalid_request."""
        response = self._grant(client_secret=None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._oauth_error(response), "invalid_request")

    def test_grant_public_client_rejected(self):
        """Test that public clients cannot use the grant (RFC 6749
        section 4.4.2 requires client authentication)."""
        response = self._grant(client_id="guest")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self._oauth_error(response), "invalid_client")

    def test_app_token_bearer_resolves_to_client_without_user(self):
        """Test that /root/authenticate resolves an app token to the
        client with no user (campus.api treats this as an app session)."""
        from campus.common import env
        token = self._grant_token()

        response = self.client.post(
            "/auth/v1/root/",
            json={"token": token}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["client"]["id"], env.get("CLIENT_ID"))
        self.assertNotIn("user", data)

    def test_app_token_authenticates_against_campus_api(self):
        """Test end-to-end: an app token passes campus.api bearer
        authentication (service-to-service read, campus-classroom#24)."""
        apps_client = self.service_manager.apps_app.test_client()
        token = self._grant_token()

        response = apps_client.get(
            "/api/v1/circles/",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 200)

    def test_revoke_app_token_invalidates_bearer(self):
        """Test RFC 7009 revocation of an app token: the bearer dies
        and the next grant mints a fresh token."""
        from campus.common import env
        token = self._grant_token()

        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "token": token,
                "client_id": env.get("CLIENT_ID"),
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 200)

        # The token no longer authenticates
        auth_response = self.client.post(
            "/auth/v1/root/",
            json={"token": token}
        )
        self.assertEqual(auth_response.status_code, 401)

        # A fresh grant issues a new token
        self.assertNotEqual(self._grant_token(), token)

    def test_revoke_app_token_wrong_client_does_not_revoke(self):
        """Test that one client cannot revoke another client's app
        token (RFC 7009 section 2.2 — response is 200, token stays
        valid)."""
        from campus.auth.resources import client as client_resource
        client_resource.new(
            id="otherappclient",
            name="Other App Client",
            description="Client that must not revoke foreign app tokens",
            is_public=True,
            redirect_uris=["urn:ietf:wg:oauth:2.0:oob"],
        )
        token = self._grant_token()

        revoke_response = self.client.post(
            "/auth/v1/oauth/revoke",
            data={
                "token": token,
                "client_id": "otherappclient",
            },
            content_type="application/x-www-form-urlencoded"
        )
        self.assertEqual(revoke_response.status_code, 200)

        # The app token was NOT revoked
        auth_response = self.client.post(
            "/auth/v1/root/",
            json={"token": token}
        )
        self.assertEqual(auth_response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
