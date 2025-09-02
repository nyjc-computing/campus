"""campus.client.vault.client

Vault client management for creating and managing vault authentication clients.
"""

from campus.client.interface import Resource
from campus.common.http import JsonResponse


class VaultClientResource(Resource):
    """Resource for Campus /vault/clients endpoint."""

    def authenticate(self, client_id: str, client_secret: str) -> JsonResponse:
        """Authenticate a vault client using client_id and client_secret.

        Args:
            client_id: The client ID
            client_secret: The client secret
        """
        data = {"client_id": client_id, "client_secret": client_secret}
        response = self.client.post(self.make_path("authenticate"), data)
        return response

    def new(self, name: str, description: str) -> JsonResponse:
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
        response = self.client.post(self.path, json=data)
        return response

    def get(self, client_id: str) -> JsonResponse:
        """Get details of a specific vault client.

        Args:
            client_id: Target client ID to retrieve

        Returns:
            Client data dictionary

        Example:
            client_info = vault.client.get("client_abc123")
            print(f"Client: {client_info['name']}")
        """
        response = self.client.get(self.make_path(client_id))
        return response

    def list(self) -> JsonResponse:
        """List all vault clients.

        Returns:
            List of client data dictionaries

        Example:
            clients = vault.client.list()
            for client in clients:
                print(f"Client: {client['name']} (ID: {client['id']})")
        """
        response = self.client.get(self.path)
        return response

    def delete(self, client_id: str) -> JsonResponse:
        """Delete a vault client.

        Args:
            client_id: Target client ID to delete

        Returns:
            Response confirming deletion

        Example:
            result = vault.client.delete("client_abc123")
            print(f"Action: {result['action']}")
        """
        response = self.client.delete(self.make_path(client_id))
        return response


__all__ = ['VaultClientResource']
