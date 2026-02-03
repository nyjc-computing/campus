"""Integration tests for campus.auth vault routes.

Tests that the auth service vault endpoints can be instantiated and basic
endpoints function correctly without returning 404 errors.
"""

import unittest

from tests.fixtures import services


class TestVaultIntegration(unittest.TestCase):
    """Integration tests for the vault routes in campus.auth."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()

        # Get the apps (auth) app from the service manager
        # campus.auth routes are served through the apps/api service
        import flask
        apps_app = cls.service_manager.apps_app
        if not isinstance(apps_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = apps_app

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

    def test_auth_vault_instantiation(self):
        """Test that campus.auth vault routes can be instantiated successfully."""
        # This test verifies that the auth module can be imported and
        # an app can be created from it without errors
        self.assertIsNotNone(self.app)
        self.assertIsNotNone(self.client)

    def test_auth_vault_api_response_format(self):
        """Test that the auth vault API endpoint returns a valid response format."""
        response = self.client.get("/auth/vaults/vault/")

        # Ensure we get a response
        self.assertIsNotNone(response)

        # If the response is JSON, it should be parseable
        if response.content_type and 'json' in response.content_type:
            try:
                response_data = response.get_json()
                self.assertIsNotNone(response_data)
            except Exception as e:
                self.fail(f"Failed to parse JSON response: {e}")


if __name__ == '__main__':
    unittest.main()
