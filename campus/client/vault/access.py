"""campus.client.vault.access

Vault access management client for managing permissions and client access.
"""

from campus.client.wrapper import JsonResponse, Resource


class VaultAccessResource(Resource):
    """Client for vault access management operations.

    Provides methods for granting, revoking, and listing client access
    permissions for vault collections and their secrets.
    """

    def grant(
            self,
            *,
            client_id: str,
            label: str,
            permissions: list[str] | int
    ) -> JsonResponse:
        """Grant access to a vault for a client.

        Args:
            client_id: Target client ID to grant access to
            label: Vault label (e.g., "apps", "storage", "oauth")
            permissions: Permission bitflags as integer (READ=1, CREATE=2, UPDATE=4, DELETE=8)
                        Can combine: READ+CREATE=3, ALL=15
        """
        data = {
            "client_id": client_id,
            "permissions": permissions
        }
        response = self.client.post(self.make_path(label), json=data)
        return response

    def revoke(self, *, client_id: str, label: str) -> JsonResponse:
        """Revoke access to a vault for a client.

        Args:
            client_id: Target client ID to revoke access from
            label: Vault label (e.g., "apps", "storage", "oauth")
        """
        data = {"client_id": client_id}
        response = self.client.delete(self.make_path(label), json=data)
        return response

    def check(self, *, client_id: str, label: str) -> JsonResponse:
        """Check if a client has access to a vault.

        Args:
            client_id: Target client ID to check
            label: Vault label
        """
        response = self.client.get(
            self.make_path(label),
            params={"client_id": client_id}
        )
        return response
