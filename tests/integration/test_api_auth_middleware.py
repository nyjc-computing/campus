"""Integration tests for campus.api request authentication.

Regression tests for #614: authentication failures on campus.api must
surface as 401 (Unauthorized), never as a 500, and campus.auth's
/root/authenticate endpoint must be callable by clients that hold only
the credentials they are trying to validate (no pre-existing session).
"""

import base64
import unittest

from campus.common import env
from tests.integration.base import IsolatedIntegrationTestCase


class TestApiAuthMiddleware(IsolatedIntegrationTestCase):
    """campus.api authentication middleware behaviour (#614)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.apps_client = cls.manager.apps_app.test_client()
        cls.auth_client = cls.manager.auth_app.test_client()

    def test_missing_authorization_returns_401(self):
        """Request without Authorization header returns 401, not 400/500."""
        response = self.apps_client.get("/api/v1/circles/")

        self.assertEqual(response.status_code, 401)

    def test_unknown_bearer_token_returns_401(self):
        """Unknown bearer token returns 401, not 500 (#614)."""
        response = self.apps_client.get(
            "/api/v1/circles/",
            headers={"Authorization": "Bearer not-a-real-token"},
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_unknown_basic_client_returns_401(self):
        """Unknown Basic credentials return 401, not 500 (#614)."""
        credentials = base64.b64encode(
            b"no-such-client:no-such-secret").decode()

        response = self.apps_client.get(
            "/api/v1/circles/",
            headers={"Authorization": f"Basic {credentials}"},
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_malformed_authorization_returns_401(self):
        """Malformed Authorization values return 401, not 500 (#725).

        "Bearer" without a token is the observed payload: curl trims a
        trailing space, so "Authorization: Bearer " arrives scheme-only.
        """
        for value in ("Bearer", "Digest abc"):
            response = self.apps_client.get(
                "/api/v1/circles/",
                headers={"Authorization": value},
            )

            self.assertEqual(response.status_code, 401, value)
            data = response.get_json()
            self.assertEqual(data["error"]["code"], "UNAUTHORIZED", value)

    def test_basic_without_separator_returns_401(self):
        """Basic credentials decoding without a separator return 401 (#725)."""
        credentials = base64.b64encode(b"no-separator").decode()

        response = self.apps_client.get(
            "/api/v1/circles/",
            headers={"Authorization": f"Basic {credentials}"},
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_root_authenticate_needs_no_prior_credentials(self):
        """POST /root/ works with only the credentials in the body.

        /root/authenticate is the authentication endpoint itself; it must
        not require an already-authenticated caller (chicken-and-egg for
        service middleware that holds only the credentials it is
        validating).
        """
        response = self.auth_client.post(
            "/auth/v1/root/",
            json={
                "client_id": env.CLIENT_ID,
                "client_secret": env.CLIENT_SECRET,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("client", data)


if __name__ == "__main__":
    unittest.main()
