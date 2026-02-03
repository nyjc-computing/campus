"""HTTP contract tests for campus.auth vault endpoints.

These tests verify the HTTP interface contract for vault operations.
They test status codes, response formats, and authentication behavior.
"""

import unittest

from campus.common import env
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers


class TestAuthVaultContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/vaults/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    def test_get_secret_no_auth_returns_401(self):
        """GET /vaults/{label}/{key} without auth returns 401."""
        response = self.client.get("/auth/v1/vaults/vault/SECRET_KEY")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error_code", data)
        self.assertEqual(data["error_code"], "UNAUTHORIZED")

    def test_get_secret_missing_returns_404(self):
        """GET /vaults/{label}/{key} for missing key returns 404."""
        response = self.client.get(
            "/auth/v1/vaults/vault/MISSING_KEY",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        # Vault endpoint returns simple error dict for 404
        self.assertIn("error", data)
        self.assertEqual(data["error"], "Key not found")

    def test_get_set_secret_round_trip(self):
        """SET then GET secret returns the value."""
        # Set a secret
        set_response = self.client.post(
            "/auth/v1/vaults/vault/TEST_KEY",
            json={"value": "test123"},
            headers=self.auth_headers
        )
        self.assertEqual(set_response.status_code, 200)
        set_data = set_response.get_json()
        self.assertEqual(set_data["key"], "test123")

        # Get it back
        get_response = self.client.get(
            "/auth/v1/vaults/vault/TEST_KEY",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 200)
        data = get_response.get_json()
        self.assertEqual(data["key"], "test123")

    def test_list_vault_keys(self):
        """GET /vaults/{label}/ returns list of keys."""
        # Set up some keys
        self.client.post(
            "/auth/v1/vaults/vault/KEY1",
            json={"value": "v1"},
            headers=self.auth_headers
        )
        self.client.post(
            "/auth/v1/vaults/vault/KEY2",
            json={"value": "v2"},
            headers=self.auth_headers
        )

        response = self.client.get(
            "/auth/v1/vaults/vault/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("keys", data)
        self.assertIn("KEY1", data["keys"])
        self.assertIn("KEY2", data["keys"])

    def test_delete_secret(self):
        """DELETE /vaults/{label}/{key} removes the secret."""
        # Set a secret
        self.client.post(
            "/auth/v1/vaults/vault/DEL_KEY",
            json={"value": "v"},
            headers=self.auth_headers
        )

        # Delete it (note: DELETE requires empty JSON body due to unpack_request decorator)
        del_response = self.client.delete(
            "/auth/v1/vaults/vault/DEL_KEY",
            json={},
            headers=self.auth_headers
        )
        self.assertEqual(del_response.status_code, 200)

        # Verify it's gone
        get_response = self.client.get(
            "/auth/v1/vaults/vault/DEL_KEY",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
