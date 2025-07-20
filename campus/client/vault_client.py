"""Campus Vault Client Management Client

Provides HTTP-like interface for vault client operations:
- vault.client.new(name, description) - POST /client
- vault.client.get(client_id) - GET /client/{client_id}
- vault.client.list() - GET /client
- vault.client.delete(client_id) - DELETE /client/{client_id}

Usage:
    import campus.client.vault as vault
    
    # Create a new client
    client_data, secret = vault.client.new("My App", "Application client")
    
    # List all clients
    clients = vault.client.list()
    
    # Get specific client
    client_info = vault.client.get("client_abc123")
    
    # Delete client
    vault.client.delete("client_abc123")
"""

from typing import List, Dict, Any, Tuple
from .base import BaseClient


class VaultClientManagement:
    """Client for vault client management operations."""
    
    def __init__(self, vault_client: BaseClient):
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
        response = self._client._post("/client", data)
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
        response = self._client._get(f"/client/{client_id}")
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
        response = self._client._get("/client")
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
        return self._client._delete(f"/client/{client_id}")
