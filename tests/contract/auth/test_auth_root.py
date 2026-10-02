"""HTTP contract tests for campus.auth root endpoint.

POST /auth/v1/root/ is the internal credential-validation endpoint used by
Campus backend services (e.g. campus.api's request middleware). These tests
pin the error envelope shapes (#714): error responses use the standard
Campus error envelope, like every other auth route.
"""

import unittest

from campus.common import env
from tests.fixtures import services


class TestAuthRootContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/root/."""

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

    def test_authenticate_missing_credentials_returns_400_envelope(self):
        """POST /root/ without credentials returns a 400 error envelope."""
        response = self.client.post("/auth/v1/root/", json={})

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_REQUEST")
        self.assertIn("message", data["error"])
        self.assertIn("request_id", data["error"])

    def test_authenticate_unknown_client_returns_400_envelope(self):
        """POST /root/ with an unknown client returns a 400 error envelope.

        An unknown client is rejected by the resources layer with
        AUTH_INVALID_REQUEST before the wrong-secret path is reached.
        """
        response = self.client.post(
            "/auth/v1/root/",
            json={"client_id": "campus_nonexistent", "client_secret": "wrong"},
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_REQUEST")
        self.assertIn("message", data["error"])
        self.assertIn("request_id", data["error"])

    def test_authenticate_invalid_client_credentials_returns_401_envelope(self):
        """POST /root/ with a wrong secret returns a 401 error envelope."""
        response = self.client.post(
            "/auth/v1/root/",
            json={"client_id": env.CLIENT_ID, "client_secret": "definitely-wrong-secret"},
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "AUTH_INVALID_CLIENT")
        self.assertIn("message", data["error"])
        self.assertIn("request_id", data["error"])

    def test_authenticate_unknown_token_returns_401_envelope(self):
        """POST /root/ with an unknown token returns a 401 error envelope."""
        response = self.client.post(
            "/auth/v1/root/",
            json={"token": "campus_unknown_token_value"},
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "AUTH_TOKEN_INVALID")
        self.assertIn("message", data["error"])
        self.assertIn("request_id", data["error"])

    def test_authenticate_valid_client_credentials_returns_client(self):
        """POST /root/ with valid client credentials returns the client."""
        response = self.client.post(
            "/auth/v1/root/",
            json={
                "client_id": env.CLIENT_ID,
                "client_secret": env.CLIENT_SECRET,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("client", data)


if __name__ == '__main__':
    unittest.main()
