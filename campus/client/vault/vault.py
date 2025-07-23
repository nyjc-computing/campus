"""client.vault.vault

Main vault client interface for secrets management and access control.
"""

# pylint: disable=attribute-defined-outside-init

import sys
from typing import List
from campus.client.base import HttpClient
from campus.client.errors import NotFoundError
from campus.client import config


class VaultCollection:
    """Represents a vault collection with HTTP-like methods.

    Provides an interface for managing secrets within a specific vault collection,
    including operations for storing, retrieving, and deleting secret values.
    """

    def __init__(self, vault_client: HttpClient, label: str):
        """Initialize vault collection.

        Args:
            vault_client: The vault client instance
            label: The vault label (e.g., "apps", "storage", "oauth")
        """
        self._client = vault_client
        self._label = label

    def get(self, key: str) -> str:
        """Get a secret value from the vault.

        Args:
            key: The secret key name

        Returns:
            str: The secret value

        Raises:
            NotFoundError: If the key doesn't exist
        """
        try:
            response = self._client._get(f"/vault/{self._label}/{key}")
            return response["value"]
        except NotFoundError as exc:
            raise NotFoundError(
                f"Secret '{key}' not found in vault '{self._label}'") from exc

    def set(self, key: str, value: str) -> str:
        """Set a secret value in the vault.

        Args:
            key: The secret key name
            value: The secret value

        Returns:
            Action performed ("created" or "updated")
        """
        response = self._client._post(
            f"/vault/{self._label}/{key}", {"value": value})
        return response.get("action", "updated")

    def delete(self, key: str) -> bool:
        """Delete a secret from the vault.

        Args:
            key: The secret key name

        Returns:
            True if deleted, False if key didn't exist
        """
        try:
            self._client._delete(f"/vault/{self._label}/{key}")
            return True
        except NotFoundError:
            return False

    def list(self) -> List[str]:
        """List all keys in the vault.

        Returns:
            List of key names
        """
        response = self._client._get(f"/vault/{self._label}/list")
        return response.get("keys", [])

    def has(self, key: str) -> bool:
        """Check if a key exists in the vault.

        Args:
            key: The secret key name

        Returns:
            True if key exists, False otherwise
        """
        try:
            self.get(key)
            return True
        except NotFoundError:
            return False


class VaultClient(HttpClient):
    """Client for vault operations following HTTP API conventions."""

    def _get_default_base_url(self) -> str:
        """Get the default base URL for the vault service.

        Returns:
            str: Base URL for the vault deployment
        """
        return config.get_service_base_url("vault")

    def __getitem__(self, label: str) -> VaultCollection:
        """Get a vault collection by label.

        Args:
            label: The vault label (e.g., "apps", "storage", "oauth")

        Returns:
            VaultCollection instance for the specified vault
        """
        return VaultCollection(self, label)

    def list_vaults(self) -> List[str]:
        """List available vault labels.

        Returns:
            List of available vault labels
        """
        response = self._get("/vault/list")
        return response.get("vaults", [])


class VaultModule:
    """Custom module wrapper that supports subscription syntax."""

    def __init__(self):
        self._client = VaultClient()
        # Import here to avoid circular imports
        from .access import VaultAccessClient
        from .client import VaultClientManagement
        self.access = VaultAccessClient(self._client)
        self.client = VaultClientManagement(self._client)

    def __getitem__(self, label: str) -> VaultCollection:
        """Support vault["apps"] syntax."""
        return self._client[label]

    def list_vaults(self) -> List[str]:
        """List available vault labels."""
        return self._client.list_vaults()

    def set_credentials(self, client_id: str, client_secret: str) -> None:
        """Set authentication credentials."""
        self._client.set_credentials(client_id, client_secret)

    @property
    def vault_client(self) -> VaultClient:
        """Direct access to the vault client instance."""
        return self._client


# Module Replacement Pattern:
# Replace this module with a custom class instance to support both:
# 1. Direct usage: vault["storage"]
# 2. Class imports: from campus.client.vault.vault import VaultModule
_module_instance = VaultModule()
# Dynamic attribute assignment for class imports - linter warnings expected
_module_instance.VaultModule = VaultModule  # type: ignore[attr-defined]
_module_instance.VaultClient = VaultClient  # type: ignore[attr-defined]
_module_instance.VaultCollection = VaultCollection  # type: ignore[attr-defined]
sys.modules[__name__] = _module_instance  # type: ignore
