"""Integration tests for login routes with trailing slashes.

This test suite ensures that login routes work correctly with trailing slashes.
Note: Routes are designed with trailing slashes (e.g., /logins/, /logins/<id>/).
Tests for routes without trailing slashes are omitted since they would trigger
308 redirects, which is expected Flask behavior for this route design.
"""

import unittest

from tests.integration.base import IntegrationTestCase


class TestLoginRoutesTrailingSlash(IntegrationTestCase):
    """Test login routes handle trailing slashes correctly."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        super().setUpClass()

        # Get the auth app from the service manager
        # Login routes are in campus.auth, not campus.api
        import flask
        auth_app = cls.service_manager.auth_app
        if not isinstance(auth_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = auth_app

    def test_post_logins_with_trailing_slash(self):
        """Test POST /auth/v1/logins/ with trailing slash works."""
        response = self.client.post(
            "/auth/v1/logins/",
            json={
                "client_id": "test-client",
                "user_id": "test@example.com",
                "agent_string": "test-agent"
            }
        )

        # Should not redirect (308)
        self.assertNotEqual(
            response.status_code, 308,
            f"POST /auth/v1/logins/ returned 308 redirect. Response: {response.data}"
        )

        # Should return 200 or an auth error (400/401/403), but not 404
        # 400 = missing auth header, 401 = invalid credentials, 403 = insufficient permissions
        self.assertNotEqual(
            response.status_code, 404,
            f"POST /auth/v1/logins/ returned 404. Response: {response.data}"
        )

    def test_get_login_with_trailing_slash(self):
        """Test GET /auth/v1/logins/<id>/ with trailing slash works."""
        session_id = "uid-campus-login_session-test-123"
        response = self.client.get(f"/auth/v1/logins/{session_id}/")

        # Should not redirect (308)
        self.assertNotEqual(
            response.status_code, 308,
            f"GET /auth/v1/logins/{session_id}/ returned 308 redirect. "
            f"Response: {response.data}"
        )

        # Should return 200, 404, or an auth error (400/401/403)
        # 400 = missing auth header, 401 = invalid credentials, 403 = insufficient permissions
        self.assertIn(
            response.status_code, [200, 400, 401, 403, 404],
            f"GET /auth/v1/logins/{session_id}/ returned unexpected status "
            f"{response.status_code}. Response: {response.data}"
        )

    def test_delete_login_with_trailing_slash(self):
        """Test DELETE /auth/v1/logins/<id>/ with trailing slash works."""
        session_id = "uid-campus-login_session-test-123"
        response = self.client.delete(f"/auth/v1/logins/{session_id}/")

        # Should not redirect (308)
        self.assertNotEqual(
            response.status_code, 308,
            f"DELETE /auth/v1/logins/{session_id}/ returned 308 redirect. "
            f"Response: {response.data}"
        )

        # Should return 200, 404, or an auth error (400/401/403)
        # 400 = missing auth header, 401 = invalid credentials, 403 = insufficient permissions
        self.assertIn(
            response.status_code, [200, 400, 401, 403, 404],
            f"DELETE /auth/v1/logins/{session_id}/ returned unexpected status "
            f"{response.status_code}. Response: {response.data}"
        )

    def test_patch_login_with_trailing_slash(self):
        """Test PATCH /auth/v1/logins/<id>/ with trailing slash works."""
        session_id = "uid-campus-login_session-test-123"
        response = self.client.patch(
            f"/auth/v1/logins/{session_id}/",
            json={"expiry_seconds": 3600}
        )

        # Should not redirect (308)
        self.assertNotEqual(
            response.status_code, 308,
            f"PATCH /auth/v1/logins/{session_id}/ returned 308 redirect. "
            f"Response: {response.data}"
        )

        # Should return 200, 404, or an auth error (400/401/403)
        # 400 = missing auth header, 401 = invalid credentials, 403 = insufficient permissions
        self.assertIn(
            response.status_code, [200, 400, 401, 403, 404],
            f"PATCH /auth/v1/logins/{session_id}/ returned unexpected status "
            f"{response.status_code}. Response: {response.data}"
        )


if __name__ == '__main__':
    unittest.main()
