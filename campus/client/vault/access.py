"""client.vault.access

Vault access management client for managing permissions and client access.
"""

from typing import List, Dict, Any, Union
from campus.client.base import BaseClient


class VaultAccessClient:
    """Client for vault access management operations.

    Provides methods for granting, revoking, and listing client access permissions
    for vault collections and their secrets.
    """

    def __init__(self, vault_client: BaseClient):
        """Initialize access client.

        Args:
            vault_client: The vault client instance
        """
        self._client = vault_client

    def grant(self, client_id: str, label: str, permissions: Union[List[str], int]) -> Dict[str, Any]:
        """Grant access to a vault for a client.

        Args:
            client_id: Target client ID to grant access to
            label: Vault label (e.g., "apps", "storage", "oauth")
            permissions: Permission bitflags as integer (READ=1, CREATE=2, UPDATE=4, DELETE=8)
                        Can combine: READ+CREATE=3, ALL=15

        Returns:
            Response with granted permissions info

        Example:
            vault.access.grant("user123", "apps", 3)  # READ + CREATE permissions
            vault.access.grant("user123", "apps", 15) # All permissions
        """
        data = {
            "client_id": client_id,
            "permissions": permissions
        }
        return self._client._post(f"/access/{label}", data)

    def revoke(self, client_id: str, label: str) -> Dict[str, Any]:
        """Revoke access to a vault for a client.

        Args:
            client_id: Target client ID to revoke access from
            label: Vault label

        Returns:
            Response confirming revocation

        Example:
            vault.access.revoke("user123", "apps")
        """
        return self._client._delete(f"/access/{label}", params={"client_id": client_id})

    def check(self, client_id: str, label: str) -> Dict[str, Any]:
        """Check if a client has access to a vault.

        Args:
            client_id: Target client ID to check
            label: Vault label

        Returns:
            Dictionary with permission details

        Example:
            permissions = vault.access.check("user123", "apps")
            print(permissions["permissions"]["READ"])  # True/False
        """
        return self._client._get(f"/access/{label}", params={"client_id": client_id})


class VaultAccessModule:
    """Custom module wrapper for vault access operations."""

    def __init__(self, vault_client: BaseClient):
        self._access_client = VaultAccessClient(vault_client)

    def grant(self, client_id: str, label: str, permissions: Union[List[str], int]) -> Dict[str, Any]:
        """Grant access to a vault for a client."""
        return self._access_client.grant(client_id, label, permissions)

    def revoke(self, client_id: str, label: str) -> Dict[str, Any]:
        """Revoke access to a vault for a client."""
        return self._access_client.revoke(client_id, label)

    def check(self, client_id: str, label: str) -> Dict[str, Any]:
        """Check if a client has access to a vault."""
        return self._access_client.check(client_id, label)

    @property
    def client(self) -> VaultAccessClient:
        """Direct access to the access client instance."""
        return self._access_client


# For module replacement pattern, we'll export the class
# The actual module replacement happens in vault.py
__all__ = ['VaultAccessClient', 'VaultAccessModule']
