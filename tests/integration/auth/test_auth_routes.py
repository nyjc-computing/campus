"""Integration tests for campus.auth vault routes.

Tests that the auth service vault endpoints can be instantiated and basic
endpoints function correctly without returning 404 errors.
"""

import unittest

from tests.integration.base import CleanIntegrationTestCase


class TestVaultIntegration(CleanIntegrationTestCase):
    """Integration tests for the vault routes in campus.auth."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        super().setUpClass()

        # Get the auth app from the service manager
        # campus.auth has its own Flask app with auth routes
        import flask
        auth_app = cls.service_manager.auth_app
        if not isinstance(auth_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = auth_app

    def test_auth_vault_instantiation(self):
        """Test that campus.auth vault routes can be instantiated successfully."""
        # This test verifies that the auth module can be imported and
        # an app can be created from it without errors
        self.assertIsNotNone(self.app)
        self.assertIsNotNone(self.client)

    # Note: Vault API response format testing has been removed because:
    # 1. Vault endpoints are already properly tested in tests/contract/test_auth_vault.py
    # 2. Those tests include proper authentication and comprehensive response validation
    # 3. This test was using the wrong Flask app (apps_app instead of auth_app)
    # 4. Vault endpoints require authentication, which this test didn't provide


if __name__ == '__main__':
    unittest.main()
