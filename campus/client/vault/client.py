"""campus.client.vault.client

Vault client management for creating and managing vault authentication clients.
"""

from campus.client.interface import Resource


class VaultClientResource(Resource):
    """Resource for Campus /vault/clients endpoint."""

    def authenticate(self, client_id: str, client_secret: str) -> dict:
        """Authenticate a vault client using client_id and client_secret.

        Args:
            client_id: The client ID
            client_secret: The client secret
        """
        data = {"client_id": client_id, "client_secret": client_secret}
        json = self._process_response(
            self.client.post(self.make_path("authenticate"), data)
        )
        return json.json()

    def new(self, name: str, description: str) -> dict[str, str]:
        """Create a new vault client.

        Args:
            name: Client name
            description: Client description

        Returns:
            {"client": client_data, "secret": client_secret}

        Example:
            client_info = vault.client.new("My App", "App description")
            print(f"Created client {client_info['client']['id']} with secret {client_info['secret']}")
        """
        data = {
            "name": name,
            "description": description
        }
        json = self._process_response(
            self.client.post(self.path, json=data)
        )
        assert isinstance(json, dict)
        return json

    def get(self, client_id: str) -> dict[str, str]:
        """Get details of a specific vault client.

        Args:
            client_id: Target client ID to retrieve

        Returns:
            Client data dictionary

        Example:
            client_info = vault.client.get("client_abc123")
            print(f"Client: {client_info['name']}")
        """
        json = self._process_response(
            self.client.get(self.make_path(client_id))
        )
        assert isinstance(json, dict)
        return json

    def list(self) -> list[dict]:
        """List all vault clients.

        Returns:
            List of client data dictionaries

        Example:
            clients = vault.client.list()
            for client in clients:
                print(f"Client: {client['name']} (ID: {client['id']})")
        """
        json = self._process_response(self.client.get(self.path))
        assert isinstance(json, list)
        return json

    def delete(self, client_id: str) -> dict:
        """Delete a vault client.

        Args:
            client_id: Target client ID to delete

        Returns:
            Response confirming deletion

        Example:
            result = vault.client.delete("client_abc123")
            print(f"Action: {result['action']}")
        """
        json = self._process_response(
            self.client.delete(self.make_path(client_id))
        )
        assert isinstance(json, dict)
        return json


__all__ = ['VaultClientResource']
