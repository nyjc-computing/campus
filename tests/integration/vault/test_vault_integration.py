"""Integration tests for campus.vault service.

Tests that the vault service can be instantiated and basic endpoints
function correctly without returning 404 errors.
"""

import unittest

# Set up environment variables before importing campus modules
from tests.fixtures import setup
setup.set_test_env_vars()
setup.set_vault_env_vars()

import campus.vault
from campus.common import devops




class TestVaultIntegration(unittest.TestCase):
    """Integration tests for the vault service."""

    def setUp(self):
        """Set up test environment before each test."""
        # Create the Flask test app using devops.deploy
        self.app = devops.deploy.create_app(campus.vault)
        self.client = self.app.test_client()
        
        # Set up test context
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        """Clean up after each test."""
        self.app_context.pop()

    def test_vault_instantiation(self):
        """Test that campus.vault can be instantiated successfully."""
        # This test verifies that the vault module can be imported and
        # an app can be created from it without errors
        self.assertIsNotNone(self.app)
        self.assertIsNotNone(self.client)

    def test_vault_api_endpoint_not_404(self):
        """Test that the vault API endpoint does not return 404."""
        # Make a GET request to the vault API endpoint
        response = self.client.get("/api/v1/vault/")
        
        # Assert that the response is not a 404 Not Found
        self.assertNotEqual(response.status_code, 404, 
                          f"Vault API endpoint returned 404. Response: {response.data}")
        
        # The endpoint might return other status codes (like 401 for unauthorized)
        # but it should exist and not return 404
        self.assertIn(response.status_code, [200, 401, 403], 
                     f"Unexpected status code: {response.status_code}. Response: {response.data}")

    def test_vault_api_response_format(self):
        """Test that the vault API endpoint returns a valid response format."""
        response = self.client.get("/api/v1/vault/")
        
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
