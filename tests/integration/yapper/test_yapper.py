import unittest

from campus.common import env
from tests.integration.base import CleanIntegrationTestCase


class TestYapper(CleanIntegrationTestCase):
    """Integration tests for Yapper service."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        super().setUpClass()
        # Set the auth app for vault access tests
        cls.app = cls.service_manager.auth_app

    def test_vault_vars_and_access(self):
        # After service setup, vault credentials should be available
        self.assertIsNotNone(env.CLIENT_SECRET)
        self.assertIsNotNone(env.CLIENT_ID)

    def test_yapper_vault_access(self):
        """Test that yapper vault data is accessible through Flask app.

        Uses the Flask test client to access the vault endpoint, verifying
        that YAPPERDB_URI is properly stored and accessible.

        Note: We don't test via campus_python.Campus() because that class
        caches CampusRequest reference at import time, before our monkey-patch
        is applied. Testing through Flask directly validates the endpoint works.
        """
        # Use self.client (provided by IntegrationTestCase base class)
        # Set basic auth headers (required by vault routes)
        import base64
        credentials = f"{env.CLIENT_ID}:{env.CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()
        headers = {"Authorization": f"Basic {encoded}"}

        response = self.client.get("/auth/v1/vaults/campus.yapper/YAPPERDB_URI", headers=headers)

        # Should get a successful response with the YAPPERDB_URI value
        self.assertEqual(response.status_code, 200,
                        f"Failed to access vault endpoint: {response.data}")
        data = response.get_json()
        self.assertIsNotNone(data.get("key"), "No key returned from vault")

    def test_yapper_init(self):
        """Test that yapper.create() successfully creates a yapper instance."""
        import campus.yapper
        self.yapperInterface = campus.yapper.create()
        self.assertIsNotNone(self.yapperInterface)


if __name__ == "__main__":
    unittest.main()
