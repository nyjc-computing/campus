"""tests/test_client_vault

Comprehensive black-box unit tests for campus.client.vault, including:
- VaultResource: Main interface for vault operations and access management
- VaultKeyResource: Individual secret operations (get, set, delete)
- VaultAccessResource: Access permission management
- VaultClientResource: Vault client authentication management

Testing Approach:
- **Black-box testing**: Tests only use public interfaces and mock external HTTP dependencies
- **No internal mocking**: Avoids mocking internal implementation details
- **HTTP layer mocking**: Mocks JsonClient methods to simulate API responses
- **Public interface focus**: Validates user-facing behavior without coupling to internal structure

This approach ensures tests remain stable during internal refactors while
thoroughly validating the public API contract that users depend on.
"""

import unittest
from unittest.mock import Mock

from campus.common.http import JsonClient
from campus.client.vault import VaultResource, VaultAccessResource, VaultClientResource
from campus.client.vault.vault import VaultKeyResource, Vault


class TestVaultKeyResource(unittest.TestCase):
    """Test cases for VaultKeyResource class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        # Create a vault resource and then get a key from it
        vault_resource = VaultResource(self.mock_client)
        vault = vault_resource["apps"]
        self.vault_key = vault["SECRET_KEY"]

    def test_init(self):
        """Test VaultKeyResource initialization."""
        self.assertEqual(self.vault_key.client, self.mock_client)
        self.assertEqual(self.vault_key.path, "vault/apps/SECRET_KEY")

    def test_get_success(self):
        """Test successful secret retrieval."""
        self.mock_client.get.return_value.json.return_value = {
            "value": "secret_value"}
        result = self.vault_key.get()
        self.assertEqual(result, {"value": "secret_value"})

    def test_set_success(self):
        """Test successful secret setting."""
        self.mock_client.post.return_value.json.return_value = {
            "value": "new_secret"}
        result = self.vault_key.set(value="new_secret")
        self.assertEqual(result, {"value": "new_secret"})

    def test_delete_success(self):
        """Test successful secret deletion."""
        self.mock_client.delete.return_value.json.return_value = {
            "deleted": True}
        result = self.vault_key.delete()
        self.assertEqual(result, {"deleted": True})


class TestVault(unittest.TestCase):
    """Test cases for Vault class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        vault_resource = VaultResource(self.mock_client)
        self.vault = vault_resource["apps"]

    def test_init(self):
        """Test Vault initialization."""
        self.assertEqual(self.vault.client, self.mock_client)
        self.assertEqual(self.vault.path, "vault/apps")

    def test_getitem(self):
        """Test getting a specific key from vault."""
        vault_key = self.vault["SECRET_KEY"]

        self.assertIsInstance(vault_key, VaultKeyResource)
        self.assertEqual(vault_key.client, self.mock_client)
        self.assertEqual(vault_key.path, "vault/apps/SECRET_KEY")

    def test_list_success(self):
        """Test listing all keys in vault."""
        self.mock_client.get.return_value.json.return_value = {
            "keys": ["KEY1", "KEY2", "KEY3"]}
        result = self.vault.list()
        self.assertEqual(result, {"keys": ["KEY1", "KEY2", "KEY3"]})


class TestVaultAccessResource(unittest.TestCase):
    """Test cases for VaultAccessResource class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        vault_resource = VaultResource(self.mock_client)
        self.access_resource = vault_resource.access

    def test_init(self):
        """Test VaultAccessResource initialization."""
        self.assertEqual(self.access_resource.client, self.mock_client)
        self.assertEqual(self.access_resource.path, "vault/access")


class TestVaultClientResource(unittest.TestCase):
    """Test cases for VaultClientResource class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        vault_resource = VaultResource(self.mock_client)
        self.client_resource = vault_resource.clients

    def test_init(self):
        """Test VaultClientResource initialization."""
        self.assertEqual(self.client_resource.client, self.mock_client)
        self.assertEqual(self.client_resource.path, "vault/clients")

    def test_authenticate_success(self):
        """Test successful client authentication."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": "success"}
        self.mock_client.post.return_value = mock_response

        result = self.client_resource.authenticate("client123", "secret456")

        self.assertEqual(result, {"status": "success"})
        self.mock_client.post.assert_called_once_with(
            "vault/clients/authenticate",
            {"client_id": "client123", "client_secret": "secret456"}
        )

    def test_new_client(self):
        """Test creating a new vault client."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "client": {"id": "client123", "name": "Test Client"},
            "client_secret": "secret456"
        }
        self.mock_client.post.return_value = mock_response

        result = self.client_resource.new("Test Client", "Description")

        self.assertEqual(result, {
            "client": {"id": "client123", "name": "Test Client"},
            "client_secret": "secret456"
        })
        self.mock_client.post.assert_called_once_with(
            "vault/clients",
            json={"name": "Test Client", "description": "Description"}
        )

    def test_get_client(self):
        """Test getting a specific vault client."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "client": {"id": "client123", "name": "Test Client"}
        }
        self.mock_client.get.return_value = mock_response

        result = self.client_resource.get("client123")

        self.assertEqual(result, {
            "client": {"id": "client123", "name": "Test Client"}
        })
        self.mock_client.get.assert_called_once_with("vault/clients/client123")

    def test_list_clients(self):
        """Test listing all vault clients."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "clients": [
                {"id": "client1", "name": "Client 1"},
                {"id": "client2", "name": "Client 2"}
            ]
        }
        self.mock_client.get.return_value = mock_response

        result = self.client_resource.list()

        self.assertEqual(result, {
            "clients": [
                {"id": "client1", "name": "Client 1"},
                {"id": "client2", "name": "Client 2"}
            ]
        })
        self.mock_client.get.assert_called_once_with("vault/clients")

    def test_delete_client(self):
        """Test deleting a vault client."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "action": "deleted",
            "client_id": "client123"
        }
        self.mock_client.delete.return_value = mock_response

        result = self.client_resource.delete("client123")

        self.assertEqual(result, {
            "action": "deleted",
            "client_id": "client123"
        })
        self.mock_client.delete.assert_called_once_with(
            "vault/clients/client123")


class TestVaultResource(unittest.TestCase):
    """Test cases for VaultResource class - black-box testing of public interface."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock(spec=JsonClient)
        self.mock_client.base_url = "https://vault.example.com"
        self.vault_resource = VaultResource(self.mock_client)

    def test_init(self):
        """Test VaultResource initialization."""
        self.assertEqual(self.vault_resource.client, self.mock_client)
        self.assertEqual(self.vault_resource.path, "vault")

    def test_getitem_returns_vault(self):
        """Test that __getitem__ returns a Vault."""
        vault = self.vault_resource["apps"]

        self.assertIsInstance(vault, Vault)
        self.assertEqual(vault.path, "vault/apps")
        self.assertEqual(vault.client, self.mock_client)

    def test_list_vaults(self):
        """Test vault discovery."""
        self.mock_client.get.return_value.json.return_value = {
            "vaults": ["apps", "storage", "oauth"]}
        result = self.vault_resource.list()
        self.assertEqual(result, {"vaults": ["apps", "storage", "oauth"]})

    def test_access_property(self):
        """Test access property returns VaultAccessResource."""
        access_resource = self.vault_resource.access

        self.assertIsInstance(access_resource, VaultAccessResource)
        self.assertEqual(access_resource.client, self.mock_client)
        self.assertEqual(access_resource.path, "vault/access")

    def test_clients_property(self):
        """Test clients property returns VaultClientResource."""
        client_resource = self.vault_resource.clients

        self.assertIsInstance(client_resource, VaultClientResource)
        self.assertEqual(client_resource.client, self.mock_client)
        self.assertEqual(client_resource.path, "vault/clients")

    def test_access_property_consistency(self):
        """Test that access property returns the same instance."""
        access1 = self.vault_resource.access
        access2 = self.vault_resource.access

        self.assertIs(access1, access2)

    def test_clients_property_consistency(self):
        """Test that clients property returns the same instance."""
        client1 = self.vault_resource.clients
        client2 = self.vault_resource.clients

        self.assertIs(client1, client2)

    # Test public interface integration (black-box testing)
    def test_vault_key_access_integration(self):
        """Test end-to-end secret access via chained indexing."""
        self.mock_client.get.return_value.json.return_value = {
            "value": "secret_value"}
        result = self.vault_resource["apps"]["SECRET_KEY"].get()
        self.assertEqual(result, {"value": "secret_value"})

    def test_vault_key_set_integration(self):
        """Test end-to-end secret storage via chained indexing."""
        self.mock_client.post.return_value.json.return_value = {
            "value": "new_value"}
        result = self.vault_resource["apps"]["SECRET_KEY"].set(
            value="new_value")
        self.assertEqual(result, {"value": "new_value"})

    def test_vault_key_delete_integration(self):
        """Test end-to-end secret deletion via chained indexing."""
        self.mock_client.delete.return_value.json.return_value = {
            "deleted": True}
        result = self.vault_resource["apps"]["SECRET_KEY"].delete()
        self.assertEqual(result, {"deleted": True})

    def test_access_integration(self):
        """Test access management via vault.access property composition."""
        mock_response = Mock()
        mock_response.json.return_value = {"granted": True}
        self.mock_client.post.return_value = mock_response

        # This would require implementing the grant method in VaultAccessResource
        # For now, just test that the property returns the right type
        access_resource = self.vault_resource.access
        self.assertIsInstance(access_resource, VaultAccessResource)

    def test_clients_integration(self):
        """Test client management via vault.clients property composition."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "client": {"id": "client123", "name": "Test"},
            "client_secret": "secret456"
        }
        self.mock_client.post.return_value = mock_response

        # Test the public interface: vault.clients.new(...)
        result = self.vault_resource.clients.new("Test", "Description")

        self.assertEqual(result, {
            "client": {"id": "client123", "name": "Test"},
            "client_secret": "secret456"
        })
        self.mock_client.post.assert_called_once_with(
            "vault/clients",
            json={"name": "Test", "description": "Description"}
        )


if __name__ == '__main__':
    unittest.main()
