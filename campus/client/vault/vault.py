"""campus.client.vault.vault

Main vault client interface for secrets management and access control.
"""

from campus.client.interface import Resource
from campus.common.http import JsonClient

from .access import VaultAccessResource
from .client import VaultClientResource


class VaultKeyResource(Resource):
    """Represents a specific key in a vault collection."""

    def get(self) -> dict:
        """Get the secret value."""
        response = self.client.get(self.path)
        return self._process_response(response)  # type: ignore[return-value]

    def set(self, *, value: str) -> dict:
        """Set the secret value."""
        data = {"value": value}
        response = self.client.post(self.path, data)
        return self._process_response(response)  # type: ignore[return-value]

    def delete(self) -> dict:
        """Delete the secret."""
        response = self.client.delete(self.path)
        return self._process_response(response)  # type: ignore[return-value]


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

    def list(self) -> dict:
        """List all keys in the vault.

        Returns:
            List of key names
        """
        response = self.client.get(self.path)
        return self._process_response(response)  # type: ignore[return-value]


class VaultResource(Resource):
    """Resource for Campus /vault endpoint."""

    def __init__(self, client: JsonClient, *, raw: bool = False):
        super().__init__(client, "vault", raw=raw)
        self._access_resource = None
        self._clients_resource = None

    def __getitem__(self, label: str) -> Vault:
        """Get a vault collection by label.

        Args:
            label: The vault label (e.g., "apps", "storage", "oauth")
        """
        return Vault(self, label)

    def list(self) -> dict:
        """List available vault labels.

        Returns:
            List of available vault labels
        """
        response = self.client.get(self.path)
        return self._process_response(response)  # type: ignore[return-value]

    @property
    def access(self) -> VaultAccessResource:
        """Vault access resource."""
        if self._access_resource is None:
            self._access_resource = VaultAccessResource(self, "access")
        return self._access_resource

    @property
    def clients(self) -> VaultClientResource:
        """Vault clients resource."""
        if self._clients_resource is None:
            self._clients_resource = VaultClientResource(self, "clients")
        return self._clients_resource
