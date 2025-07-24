"""client.vault.client

Vault client management for creating and managing vault authentication clients.
"""

from typing import List, Dict, Any, Tuple
from campus.client.base import HttpClient


class VaultClientManagement:
    """Client for vault client management operations.

    Provides methods for creating, listing, and deleting vault authentication
    clients that can access vault secrets with appropriate permissions.
    """

    def __init__(self, vault_client: HttpClient):
        """Initialize client management.

        Args:
            vault_client: The vault client instance
        """
        self._client = vault_client

    def new(self, name: str, description: str) -> Tuple[Dict[str, Any], str]:
        """Create a new vault client.

        Args:
            name: Client name
            description: Client description

        Returns:
            Tuple of (client_data, client_secret)

        Example:
            client_data, secret = vault.client.new("My App", "App description")
            print(f"Created client {client_data['id']} with secret {secret}")
        """
        data = {
            "name": name,
            "description": description
        }
        response = self._client.post("/client", data)
        client_data = response["client"]
        client_secret = response["client_secret"]
        return client_data, client_secret

    def get(self, client_id: str) -> Dict[str, Any]:
        """Get details of a specific vault client.

        Args:
            client_id: Target client ID to retrieve

        Returns:
            Client data dictionary

        Example:
            client_info = vault.client.get("client_abc123")
            print(f"Client: {client_info['name']}")
        """
        response = self._client.get(f"/client/{client_id}")
        return response["client"]

    def list(self) -> List[Dict[str, Any]]:
        """List all vault clients.

        Returns:
            List of client data dictionaries

        Example:
            clients = vault.client.list()
            for client in clients:
                print(f"Client: {client['name']} (ID: {client['id']})")
        """
        response = self._client.get("/client")
        return response["clients"]

    def delete(self, client_id: str) -> Dict[str, Any]:
        """Delete a vault client.

        Args:
            client_id: Target client ID to delete

        Returns:
            Response confirming deletion

        Example:
            result = vault.client.delete("client_abc123")
            print(f"Action: {result['action']}")
        """
        return self._client.delete(f"/client/{client_id}")


class VaultClientModule:
    """Custom module wrapper for vault client management operations."""

    def __init__(self, vault_client: HttpClient):
        self._client_mgmt = VaultClientManagement(vault_client)

    def new(self, name: str, description: str) -> Tuple[Dict[str, Any], str]:
        """Create a new vault client."""
        return self._client_mgmt.new(name, description)

    def get(self, client_id: str) -> Dict[str, Any]:
        """Get details of a specific vault client."""
        return self._client_mgmt.get(client_id)

    def list(self) -> List[Dict[str, Any]]:
        """List all vault clients."""
        return self._client_mgmt.list()

    def delete(self, client_id: str) -> Dict[str, Any]:
        """Delete a vault client."""
        return self._client_mgmt.delete(client_id)

    @property
    def client(self) -> VaultClientManagement:
        """Direct access to the client management instance."""
        return self._client_mgmt


# For module replacement pattern, we'll export the class
# The actual module replacement happens in vault.py
__all__ = ['VaultClientManagement', 'VaultClientModule']
