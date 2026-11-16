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
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    def test_get_secret_no_auth_returns_401(self):
        """GET /vaults/{label}/{key} without auth returns 401."""
        response = self.client.get("/auth/v1/vaults/vault/SECRET_KEY/")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_get_secret_missing_returns_404(self):
        """GET /vaults/{label}/{key} for missing key returns 404."""
        response = self.client.get(
            "/auth/v1/vaults/vault/MISSING_KEY/",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "NOT_FOUND")
        self.assertIn("message", data["error"])
        self.assertIn("request_id", data["error"])

    def test_get_set_secret_round_trip(self):
        """SET then GET secret returns the value."""
        # Set a secret
        set_response = self.client.post(
            "/auth/v1/vaults/vault/TEST_KEY/",
            json={"value": "test123"},
            headers=self.auth_headers
        )
        self.assertEqual(set_response.status_code, 200)
        set_data = set_response.get_json()
        self.assertEqual(set_data["key"], "test123")

        # Get it back
        get_response = self.client.get(
            "/auth/v1/vaults/vault/TEST_KEY/",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 200)
        data = get_response.get_json()
        self.assertEqual(data["key"], "test123")

    def test_list_vault_keys(self):
        """GET /vaults/{label}/ returns list of keys."""
        # Set up some keys
        self.client.post(
            "/auth/v1/vaults/vault/KEY1/",
            json={"value": "v1"},
            headers=self.auth_headers
        )
        self.client.post(
            "/auth/v1/vaults/vault/KEY2/",
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
            "/auth/v1/vaults/vault/DEL_KEY/",
            json={"value": "v"},
            headers=self.auth_headers
        )

        # Delete it (note: DELETE requires empty JSON body due to unpack_request decorator)
        del_response = self.client.delete(
            "/auth/v1/vaults/vault/DEL_KEY/",
            json={},
            headers=self.auth_headers
        )
        self.assertEqual(del_response.status_code, 200)

        # Verify it's gone
        get_response = self.client.get(
            "/auth/v1/vaults/vault/DEL_KEY/",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 404)


class TestVaultLabelEnumeration(unittest.TestCase):
    """GET /vaults/ — the label enumeration for the admin view (#1055).

    Labels are groupings, not secrets, but the enumeration is an
    administrative view: the operator, the super-admin root, and
    designated users holding any vault grant row plus the vaults:read
    scope; client principals stay per-label (#881).
    """

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.initialize()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.cleanup()

    def setUp(self):
        self.manager.clear_test_data()
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(
            env.CLIENT_ID, env.CLIENT_SECRET
        )

    def test_labels_for_operator(self):
        """The operator enumerates labels; the seeded label is there."""
        self.client.post(
            "/auth/v1/vaults/vault/ENUM_KEY/",
            json={"value": "x"},
            headers=self.auth_headers,
        )

        response = self.client.get("/auth/v1/vaults/", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        labels = response.get_json()["labels"]
        self.assertIn("vault", labels)

    def test_labels_denied_for_client_principal(self):
        """A non-operator client cannot enumerate labels (#881)."""
        from tests.fixtures.tokens import create_test_client_credentials

        other_id, other_secret = create_test_client_credentials(
            name="1055-vault-enum-denied",
            description="Non-operator client for #1055",
        )
        headers = get_basic_auth_headers(other_id, other_secret)

        response = self.client.get("/auth/v1/vaults/", headers=headers)

        self.assertEqual(response.status_code, 403)
        self.assertIn("per-label", response.get_json()["error"]["message"])

    def test_labels_for_designated_user_with_grant_and_scope(self):
        """Any vault grant row + vaults:read scope enumerates (#1055)."""
        from campus.auth.resources.grant import grants as grants_store
        from tests.fixtures.tokens import (
            create_test_token,
            get_bearer_auth_headers,
        )

        user_id = "authz.1055.vault.enum@campus.test"
        grants_store.grant(
            "user", user_id, "vault", resource_id="vault", level="read"
        )
        token = create_test_token(
            user_id,
            scopes=["vaults:read"],
            grant_vault_access=False,
        )
        headers = get_bearer_auth_headers(token)

        response = self.client.get("/auth/v1/vaults/", headers=headers)

        self.assertEqual(response.status_code, 200)
        self.assertIn("labels", response.get_json())

    def test_labels_denied_for_user_without_grant(self):
        """Scope without a vault grant row enumerates nothing."""
        from tests.fixtures.tokens import (
            create_test_token,
            get_bearer_auth_headers,
        )

        token = create_test_token(
            "authz.1055.vault.scopeless@campus.test",
            scopes=["vaults:read"],
            grant_vault_access=False,
        )
        headers = get_bearer_auth_headers(token)

        response = self.client.get("/auth/v1/vaults/", headers=headers)

        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
