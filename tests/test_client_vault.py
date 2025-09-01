"""tests/test_client_apps

Comprehensive black-box unit tests for campus.client.vault, including:
- VaultClient: Main interface for vault operations and access management
- VaultCollection: Collection-based access to vault secrets by label
- VaultKey: Individual secret operations (get, set, delete)
- VaultAccessClient: Access permission management
- VaultClientManagement: Vault client authentication management

Testing Approach:
- **Black-box testing**: Tests only use public interfaces and mock external HTTP dependencies
- **No internal mocking**: Avoids mocking internal implementation details like composition patterns
- **HTTP layer mocking**: Mocks campus.client.base.HttpClient methods to simulate API responses
- **Public interface focus**: Validates user-facing behavior without coupling to internal structure

This approach ensures tests remain stable during internal refactors (e.g., inheritance to composition)
while thoroughly validating the public API contract that users depend on.
"""

import unittest
from unittest.mock import Mock, patch

from campus.client.errors import NotFoundError
from campus.client.vault import VaultClient
from campus.client.vault.access import VaultAccessClient
from campus.client.vault.client import VaultClientManagement
from campus.client.vault.vault import VaultCollection, VaultKey


class TestVaultKey(unittest.TestCase):
    """Test cases for VaultKey class.

    VaultKey represents an individual secret within a vault collection,
    providing operations to get, set, and delete secret values.
    Tests verify the HTTP API interaction patterns for secret management.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock()
        self.vault_key = VaultKey(self.mock_client, "apps", "SECRET_KEY")

    def test_init(self):
        """Test VaultKey initialization with client, label, and key name.

        Verifies that VaultKey properly stores the HTTP client reference
        and the vault coordinates (label and key name) for API calls.
        """
        self.assertEqual(self.vault_key._client, self.mock_client)
        self.assertEqual(self.vault_key._label, "apps")
        self.assertEqual(self.vault_key._key, "SECRET_KEY")

    def test_get_success(self):
        """Test successful secret retrieval via GET /vault/{label}/{key}.

        Verifies that VaultKey.get() correctly calls the vault API endpoint
        and extracts the secret value from the JSON response.
        """
        self.mock_client.get.return_value = {"value": "secret_value"}

        result = self.vault_key.get()

        self.assertEqual(result, "secret_value")
        self.mock_client.get.assert_called_once_with("/vault/apps/SECRET_KEY")

    def test_get_not_found(self):
        """Test secret retrieval error handling when key doesn't exist.

        Verifies that VaultKey.get() properly propagates NotFoundError
        from the HTTP client when the secret key is not found.
        """
        self.mock_client.get.side_effect = NotFoundError(
            {"error": "Key not found"})

        with self.assertRaises(NotFoundError):
            self.vault_key.get()

    def test_set_success(self):
        """Test successful secret setting via POST /vault/{label}/{key}.

        Verifies that VaultKey.set() correctly sends the secret value
        in the request body and returns the stored value from the response.
        """
        self.mock_client.post.return_value = {"value": "new_secret"}

        result = self.vault_key.set(value="new_secret")

        self.assertEqual(result, "new_secret")
        self.mock_client.post.assert_called_once_with(
            "/vault/apps/SECRET_KEY",
            {"value": "new_secret"}
        )

    def test_set_no_return_value(self):
        """Test secret setting fallback when API response omits value field.

        Verifies that VaultKey.set() returns the input value when the API
        response doesn't include a 'value' field, providing consistent behavior.
        """
        self.mock_client.post.return_value = {"status": "success"}

        result = self.vault_key.set(value="new_secret")

        self.assertEqual(result, "new_secret")

    def test_delete_success(self):
        """Test successful secret deletion via DELETE /vault/{label}/{key}.

        Verifies that VaultKey.delete() correctly calls the vault API endpoint
        and returns True to indicate successful deletion.
        """
        self.mock_client.delete.return_value = {"deleted": True}

        result = self.vault_key.delete()

        self.assertTrue(result)
        self.mock_client.delete.assert_called_once_with(
            "/vault/apps/SECRET_KEY")

    def test_delete_not_found(self):
        """Test secret deletion when key doesn't exist."""
        self.mock_client.delete.side_effect = NotFoundError(
            {"error": "Key not found"})

        with self.assertRaises(NotFoundError) as context:
            self.vault_key.delete()

        self.assertIn(
            "Secret 'SECRET_KEY' not found in vault 'apps'", str(context.exception))

    def test_str_method(self):
        """Test string representation (convenience method)."""
        self.mock_client.get.return_value = {"value": "string_value"}

        result = str(self.vault_key)

        self.assertEqual(result, "string_value")


class TestVaultCollection(unittest.TestCase):
    """Test cases for VaultCollection class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_client = Mock()
        self.vault_collection = VaultCollection(self.mock_client, "apps")

    def test_init(self):
        """Test VaultCollection initialization."""
        self.assertEqual(self.vault_collection._client, self.mock_client)
        self.assertEqual(self.vault_collection._label, "apps")

    def test_getitem(self):
        """Test getting a specific key from collection."""
        vault_key = self.vault_collection["SECRET_KEY"]

        self.assertIsInstance(vault_key, VaultKey)
        self.assertEqual(vault_key._client, self.mock_client)
        self.assertEqual(vault_key._label, "apps")
        self.assertEqual(vault_key._key, "SECRET_KEY")

    def test_list_success(self):
        """Test listing all keys in vault."""
        self.mock_client.get.return_value = {"keys": ["KEY1", "KEY2", "KEY3"]}

        result = self.vault_collection.list()

        self.assertEqual(result, ["KEY1", "KEY2", "KEY3"])
        self.mock_client.get.assert_called_once_with("/vault/apps/list")

    def test_list_empty(self):
        """Test listing keys when vault is empty."""
        self.mock_client.get.return_value = {}

        result = self.vault_collection.list()

        self.assertEqual(result, [])


class TestVaultAccessClient(unittest.TestCase):
    """Test cases for VaultAccessClient class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_vault_client = Mock()
        self.access_client = VaultAccessClient(self.mock_vault_client)

    def test_init(self):
        """Test VaultAccessClient initialization."""
        self.assertEqual(self.access_client._client, self.mock_vault_client)

    def test_grant_with_permissions_int(self):
        """Test granting access with integer permissions."""
        self.mock_vault_client.post.return_value = {"granted": True}

        result = self.access_client.grant(
            client_id="user123",
            label="apps",
            permissions=15
        )

        self.assertEqual(result, {"granted": True})
        self.mock_vault_client.post.assert_called_once_with(
            "/access/apps",
            {"client_id": "user123", "permissions": 15}
        )

    def test_grant_with_permissions_list(self):
        """Test granting access with list permissions."""
        self.mock_vault_client.post.return_value = {"granted": True}

        result = self.access_client.grant(
            client_id="user123",
            label="apps",
            permissions=["READ", "CREATE"]
        )

        self.assertEqual(result, {"granted": True})
        self.mock_vault_client.post.assert_called_once_with(
            "/access/apps",
            {"client_id": "user123", "permissions": ["READ", "CREATE"]}
        )

    def test_revoke(self):
        """Test revoking access."""
        self.mock_vault_client.delete.return_value = {"revoked": True}

        result = self.access_client.revoke(
            client_id="user123",
            label="apps"
        )

        self.assertEqual(result, {"revoked": True})
        self.mock_vault_client.delete.assert_called_once_with(
            "/access/apps",
            {"client_id": "user123"}
        )

    def test_check(self):
        """Test checking client access."""
        self.mock_vault_client.get.return_value = {
            "permissions": {"READ": True, "CREATE": False}
        }

        result = self.access_client.check(
            client_id="user123",
            label="apps"
        )

        self.assertEqual(
            result, {"permissions": {"READ": True, "CREATE": False}})
        self.mock_vault_client.get.assert_called_once_with(
            "/access/apps",
            params={"client_id": "user123"}
        )


class TestVaultClientManagement(unittest.TestCase):
    """Test cases for VaultClientManagement class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_vault_client = Mock()
        self.client_mgmt = VaultClientManagement(self.mock_vault_client)

    def test_init(self):
        """Test VaultClientManagement initialization."""
        self.assertEqual(self.client_mgmt._client, self.mock_vault_client)

    def test_authenticate_success(self):
        """Test successful client authentication."""
        self.mock_vault_client.post.return_value = {"status": "success"}

        result = self.client_mgmt.authenticate("client123", "secret456")

        self.assertTrue(result)
        self.mock_vault_client.post.assert_called_once_with(
            "/client/authenticate",
            {"client_id": "client123", "client_secret": "secret456"}
        )

    def test_authenticate_failure(self):
        """Test failed client authentication."""
        self.mock_vault_client.post.return_value = {
            "status": "error",
            "error": "Invalid credentials"
        }

        with self.assertRaises(Exception) as context:
            self.client_mgmt.authenticate("client123", "wrong_secret")

        self.assertIn("Invalid credentials", str(context.exception))

    def test_authenticate_failure_no_error_message(self):
        """Test failed authentication with no error message."""
        self.mock_vault_client.post.return_value = {"status": "error"}

        with self.assertRaises(Exception) as context:
            self.client_mgmt.authenticate("client123", "wrong_secret")

        self.assertIn("Authentication failed", str(context.exception))

    def test_new_client(self):
        """Test creating a new vault client."""
        self.mock_vault_client.post.return_value = {
            "client": {"id": "client123", "name": "Test Client"},
            "client_secret": "secret456"
        }

        client_data, client_secret = self.client_mgmt.new(
            "Test Client", "Description")

        self.assertEqual(
            client_data, {"id": "client123", "name": "Test Client"})
        self.assertEqual(client_secret, "secret456")
        self.mock_vault_client.post.assert_called_once_with(
            "/client",
            {"name": "Test Client", "description": "Description"}
        )

    def test_get_client(self):
        """Test getting a specific vault client."""
        self.mock_vault_client.get.return_value = {
            "client": {"id": "client123", "name": "Test Client"}
        }

        result = self.client_mgmt.get("client123")

        self.assertEqual(result, {"id": "client123", "name": "Test Client"})
        self.mock_vault_client.get.assert_called_once_with("/client/client123")

    def test_list_clients(self):
        """Test listing all vault clients."""
        self.mock_vault_client.get.return_value = {
            "clients": [
                {"id": "client1", "name": "Client 1"},
                {"id": "client2", "name": "Client 2"}
            ]
        }

        result = self.client_mgmt.list()

        expected = [
            {"id": "client1", "name": "Client 1"},
            {"id": "client2", "name": "Client 2"}
        ]
        self.assertEqual(result, expected)
        self.mock_vault_client.get.assert_called_once_with("/client")

    def test_delete_client(self):
        """Test deleting a vault client."""
        self.mock_vault_client.delete.return_value = {
            "action": "deleted",
            "client_id": "client123"
        }

        result = self.client_mgmt.delete("client123")

        self.assertEqual(
            result, {"action": "deleted", "client_id": "client123"})
        self.mock_vault_client.delete.assert_called_once_with(
            "/client/client123")


class TestVaultClient(unittest.TestCase):
    """Test cases for VaultClient class - black-box testing of public interface.

    VaultClient is the main entry point for vault operations, providing:
    - Vault collection access via indexing (vault["apps"])
    - Vault listing and management
    - Access to sub-clients for permissions (vault.access) and client management (vault.client)

    These tests use black-box methodology:
    - Mock HTTP requests at the HttpClient level, not internal attributes
    - Test only public interfaces that users interact with
    - Verify end-to-end behavior from user perspective
    """

    @patch('campus.config.get_base_url')
    def setUp(self, mock_get_base_url):
        """Set up test fixtures with mocked configuration."""
        mock_get_base_url.return_value = "https://vault.example.com"
        self.vault_client = VaultClient()

    def test_init_default_base_url(self):
        """Test VaultClient initialization loads base URL from configuration.

        Verifies that VaultClient properly integrates with the campus configuration
        system to load the default vault service URL.
        """
        with patch('campus.config.get_base_url') as mock_get_base_url:
            mock_get_base_url.return_value = "https://vault.default.com"
            client = VaultClient()
            mock_get_base_url.assert_called_once_with("campus.vault")
            self.assertEqual(client._client.base_url,
                             "https://vault.default.com")

    def test_init_custom_base_url(self):
        """Test VaultClient initialization with custom base URL."""
        client = VaultClient("https://custom.vault.com")
        self.assertEqual(client._client.base_url, "https://custom.vault.com")

    def test_getitem_returns_vault_collection(self):
        """Test that __getitem__ returns a VaultCollection."""
        collection = self.vault_client["apps"]

        self.assertIsInstance(collection, VaultCollection)
        self.assertEqual(collection._label, "apps")
        self.assertEqual(collection._client, self.vault_client._client)

    @patch('campus.client.base.HttpClient.get')
    def test_list_vaults(self, mock_get):
        """Test vault discovery via GET /vault/list.

        Verifies that users can discover available vault collections
        through the main VaultClient interface, receiving a list of
        vault labels that can be accessed via indexing.
        """
        mock_get.return_value = {"vaults": ["apps", "storage", "oauth"]}

        result = self.vault_client.list_vaults()

        self.assertEqual(result, ["apps", "storage", "oauth"])
        mock_get.assert_called_once_with("/vault/list")

    @patch('campus.client.base.HttpClient.get')
    def test_list_vaults_empty(self, mock_get):
        """Test vault discovery when no vaults are configured.

        Verifies graceful handling when the vault service has no
        configured vault collections, returning an empty list.
        """
        mock_get.return_value = {}

        result = self.vault_client.list_vaults()

        self.assertEqual(result, [])

    def test_access_property(self):
        """Test access property returns VaultAccessClient."""
        access_client = self.vault_client.access

        self.assertIsInstance(access_client, VaultAccessClient)
        self.assertEqual(access_client._client, self.vault_client._client)

    def test_client_property(self):
        """Test client property returns VaultClientManagement."""
        client_mgmt = self.vault_client.client

        self.assertIsInstance(client_mgmt, VaultClientManagement)
        self.assertEqual(client_mgmt._client, self.vault_client._client)

    def test_access_property_consistency(self):
        """Test that access property returns the same instance."""
        access1 = self.vault_client.access
        access2 = self.vault_client.access

        self.assertIs(access1, access2)

    def test_client_property_consistency(self):
        """Test that client property returns the same instance."""
        client1 = self.vault_client.client
        client2 = self.vault_client.client

        self.assertIs(client1, client2)

    # Test public interface integration (black-box testing)
    @patch('campus.client.base.HttpClient.get')
    def test_vault_collection_key_access(self, mock_get):
        """Test end-to-end secret access via chained indexing: vault['label']['key'].get().

        Validates the complete user workflow for accessing secrets:
        1. Index into vault collection by label
        2. Index into specific key within collection  
        3. Call get() to retrieve secret value
        This tests the full object composition chain without internal mocking.
        """
        mock_get.return_value = {"value": "secret_value"}

        # Test the public interface: vault["apps"]["SECRET_KEY"].get()
        result = self.vault_client["apps"]["SECRET_KEY"].get()

        self.assertEqual(result, "secret_value")
        mock_get.assert_called_once_with("/vault/apps/SECRET_KEY")

    @patch('campus.client.base.HttpClient.post')
    def test_vault_collection_key_set(self, mock_post):
        """Test end-to-end secret storage via chained indexing: vault['label']['key'].set().

        Validates the complete user workflow for storing secrets:
        1. Index into vault collection by label
        2. Index into specific key within collection
        3. Call set() with secret value to store
        This tests the full object composition chain for write operations.
        """
        mock_post.return_value = {"value": "new_value"}

        # Test the public interface: vault["apps"]["SECRET_KEY"].set(value="new_value")
        result = self.vault_client["apps"]["SECRET_KEY"].set(value="new_value")

        self.assertEqual(result, "new_value")
        mock_post.assert_called_once_with(
            "/vault/apps/SECRET_KEY", {"value": "new_value"})

    @patch('campus.client.base.HttpClient.delete')
    def test_vault_collection_key_delete(self, mock_delete):
        """Test end-to-end secret deletion via chained indexing: vault['label']['key'].delete().

        Validates the complete user workflow for removing secrets:
        1. Index into vault collection by label
        2. Index into specific key within collection
        3. Call delete() to remove the secret
        This tests the full object composition chain for delete operations.
        """
        mock_delete.return_value = {"deleted": True}

        # Test the public interface: vault["apps"]["SECRET_KEY"].delete()
        result = self.vault_client["apps"]["SECRET_KEY"].delete()

        self.assertTrue(result)
        mock_delete.assert_called_once_with("/vault/apps/SECRET_KEY")

    @patch('campus.client.base.HttpClient.post')
    def test_access_grant_through_property(self, mock_post):
        """Test access management via vault.access property composition.

        Validates the access management sub-client integration:
        1. Access the permissions management client via vault.access
        2. Grant permissions using the composed client interface
        This tests the property-based client composition pattern.
        """
        mock_post.return_value = {"granted": True}

        # Test the public interface: vault.access.grant(...)
        result = self.vault_client.access.grant(
            client_id="user123",
            label="apps",
            permissions=15
        )

        self.assertEqual(result, {"granted": True})
        mock_post.assert_called_once_with(
            "/access/apps",
            {"client_id": "user123", "permissions": 15}
        )

    @patch('campus.client.base.HttpClient.post')
    def test_client_new_through_property(self, mock_post):
        """Test client management via vault.client property composition.

        Validates the client management sub-client integration:
        1. Access the client management client via vault.client
        2. Create new authentication clients using the composed interface
        This tests the property-based client composition for authentication management.
        """
        mock_post.return_value = {
            "client": {"id": "client123", "name": "Test"},
            "client_secret": "secret456"
        }

        # Test the public interface: vault.client.new(...)
        client_data, secret = self.vault_client.client.new(
            "Test", "Description")

        self.assertEqual(client_data, {"id": "client123", "name": "Test"})
        self.assertEqual(secret, "secret456")
        mock_post.assert_called_once_with(
            "/client",
            {"name": "Test", "description": "Description"}
        )


if __name__ == '__main__':
    unittest.main()
