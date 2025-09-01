"""campus.client.vault.vault

Main vault client interface for secrets management and access control.
"""

from campus.client.interface import Resource
from campus.common.http import JsonClient, JsonResponse

from .access import VaultAccessResource
from .client import VaultClientResource


class VaultKeyResource(Resource):
    """Represents a specific key in a vault collection."""

    def get(self) -> JsonResponse:
        """Get the secret value."""
        response = self.client.get(self.path)
        return response

    def set(self, *, value: str) -> JsonResponse:
        """Set the secret value."""
        data = {"value": value}
        response = self.client.post(self.path, data)
        return response

    def delete(self) -> JsonResponse:
        """Delete the secret."""
        response = self.client.delete(self.path)
        return response


class Vault(Resource):
    """Represents a single vault, a collection of vault keys."""

    def __getitem__(self, key: str) -> VaultKeyResource:
        """Get a specific key in this vault collection.

        Args:
            key: The secret key name

        Returns:
            VaultKey: Object for accessing the specific secret
        """
        return VaultKeyResource(self, key)

    def list(self) -> JsonResponse:
        """List all keys in the vault.

        Returns:
            List of key names
        """
        response = self.client.get(self.path)
        return response


class VaultResource(Resource):
    """Resource for Campus /vault endpoint."""

    def __init__(self, client: JsonClient):
        super().__init__(client, "vault")

    def __getitem__(self, label: str) -> Vault:
        """Get a vault collection by label.

        Args:
            label: The vault label (e.g., "apps", "storage", "oauth")
        """
        return Vault(self, label)

    def list(self) -> JsonResponse:
        """List available vault labels.

        Returns:
            List of available vault labels
        """
        response = self.client.get(self.path)
        return response

    @property
    def access(self) -> VaultAccessResource:
        """Vault access resource."""
        return VaultAccessResource(self, "access")

    @property
    def clients(self) -> VaultClientResource:
        """Vault clients resource."""
        return VaultClientResource(self, "clients")
