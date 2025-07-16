"""vault

Vault service for managing secrets and sensitive system data in Campus.

Each vault is identified by a unique label and stores key-value pairs of secrets.
Client access to vault labels is controlled through bitflag permissions.
Clients are identified and authenticated using CLIENT_ID and CLIENT_SECRET environment variables.

DATABASE ACCESS:
This service uses direct PostgreSQL connectivity instead of the storage module
to avoid circular dependencies. Since other services may depend on vault for
secrets management, vault must be independent of the storage layer. The vault
connects directly to PostgreSQL using the VAULTDB_URI environment variable.

CLIENT AUTHENTICATION:
The vault service maintains its own client storage system to avoid circular
dependencies with the main client model. Vault clients are stored in the
vault_clients table and authenticated using client ID and secret pairs.

Both CLIENT_ID and CLIENT_SECRET environment variables must be set:
- CLIENT_ID: Identifies the client making the request
- CLIENT_SECRET: Authenticates the client's identity

PERMISSION SYSTEM:
The vault uses bitflag permissions to control what operations clients can perform:

- READ (1): Can retrieve existing secrets with vault.get()
- CREATE (2): Can add new secrets with vault.set() (for new keys)
- UPDATE (4): Can modify existing secrets with vault.set() (for existing keys)  
- DELETE (8): Can remove secrets with vault.delete()

Permissions can be combined using the | operator:
- READ | CREATE: Can read and create, but not update or delete
- READ | UPDATE: Can read and modify existing secrets
- ALL: Can perform all operations (READ | CREATE | UPDATE | DELETE)

USAGE EXAMPLE:
    # Create vault client (typically done by admin)
    from vault.client import create_client
    client_resource, client_secret = create_client(
        name="my-app", 
        description="My application"
    )
    
    # Grant permissions (typically done by admin)
    from vault.access import grant_access, READ, CREATE
    grant_access(client_resource["id"], "api-secrets", READ | CREATE)
    
    # Use vault (CLIENT_ID and CLIENT_SECRET env vars must be set)
    # CLIENT_ID=<client_id> CLIENT_SECRET=<client_secret>
    vault = get_vault("api-secrets")
    vault.set("api_key", "secret123")  # Requires CREATE (new key)
    secret = vault.get("api_key")      # Requires READ
    vault.set("api_key", "newsecret")  # Requires UPDATE (existing key)
    vault.delete("api_key")            # Requires DELETE - would fail!
"""

import os

from campus.common.utils import uid, utc_time
from campus.common import devops

from . import access, db, client

TABLE = "vault"

__all__ = [
    "get_vault",
    "Vault",
    "VaultAccessDeniedError",
    "VaultKeyError",
    "init_db",
    "client",
]


def get_vault(label: str) -> "Vault":
    """Get a Vault instance by label using the CLIENT_ID environment variable."""
    if not isinstance(label, str):
        raise TypeError(f"label must be a string, got {type(label).__name__}")
    return Vault(label)


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    """
    # Initialize vault table
    with db.get_connection_context() as conn:
        with conn.cursor() as cursor:
            vault_schema = """
                CREATE TABLE IF NOT EXISTS vault (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    label TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    UNIQUE(label, key)
                )
            """
            cursor.execute(vault_schema)

    # Initialize access control table
    access.init_db()

    # Initialize vault client table
    client.init_db()


class VaultAccessDeniedError(ValueError):
    """Custom error for when a client doesn't have access to a vault label."""

    def __init__(self, client_id: str, label: str):
        super().__init__(
            f"Client '{client_id}' does not have access to vault label '{label}'.")
        self.client_id = client_id
        self.label = label


class VaultKeyError(KeyError):
    """Custom error for when a key is not found in the vault."""

    def __init__(self, key: str):
        super().__init__(f"Key '{key}' not found in vault.")
        self.key = key


class Vault:
    """Vault model for managing secrets in the Campus system.

    A vault stores secrets as key-value pairs in a table.
    Each secret is stored as a separate row with label, key, and value.
    The vault is recognised by a unique label and access is controlled per client.

    CLIENT AUTHENTICATION:
    Client identity is determined by the CLIENT_ID environment variable.
    Client authentication is performed using the CLIENT_SECRET environment variable.
    Both environment variables must be set for vault operations to succeed.

    The vault authenticates clients using its own client storage system to avoid
    circular dependencies with the main storage layer.
    """

    def __init__(self, label: str):
        self.label = label

        # Get client credentials from environment
        client_id = os.environ.get("CLIENT_ID")
        client_secret = os.environ.get("CLIENT_SECRET")

        if not client_id:
            raise ValueError("CLIENT_ID environment variable is required")
        if not client_secret:
            raise ValueError("CLIENT_SECRET environment variable is required")

        # Authenticate the client
        try:
            client.authenticate_client(client_id, client_secret)
        except client.ClientAuthenticationError as e:
            raise ValueError(f"Client authentication failed: {e}") from e

        self.client_id = client_id

    def __repr__(self) -> str:
        return f"Vault(label={self.label!r})"

    def _check_access(self, required_permission: int) -> None:
        """Check if the client has the required permission for this vault label.

        This method uses bitwise operations to verify permissions:
        1. Calls access.has_access() which does: (granted & required) == required
        2. If access is denied, builds a human-readable error message
        3. The error message shows which specific permissions are missing

        BITWISE PERMISSION CHECKING:
        - Client granted: READ | CREATE (value: 3, binary: 0011)
        - Required: UPDATE (value: 4, binary: 0100)  
        - Check: (3 & 4) == 4 → (0011 & 0100) == 0100 → 0000 == 0100 → False
        - Result: Access denied, UPDATE permission missing

        Args:
            required_permission: The permission bitflag required for the operation
                                Can be READ (1), CREATE (2), UPDATE (4), or DELETE (8)

        Raises:
            VaultAccessDeniedError: If the client lacks the required permission.
                                   Error message includes which permissions are missing.
        """
        if not access.has_access(self.client_id, self.label, required_permission):
            permission_names = []
            if required_permission & access.READ:
                permission_names.append("READ")
            if required_permission & access.CREATE:
                permission_names.append("CREATE")
            if required_permission & access.UPDATE:
                permission_names.append("UPDATE")
            if required_permission & access.DELETE:
                permission_names.append("DELETE")

            permission_str = (
                "|".join(permission_names) if permission_names
                else str(required_permission)
            )
            raise VaultAccessDeniedError(
                self.client_id,
                f"{self.label} (missing {permission_str} permission)"
            )

    def get(self, key: str) -> str:
        """Get a secret from the vault.

        Requires READ permission. This is the most basic operation and is typically
        granted to most clients that need access to secrets.

        Args:
            key: The secret key name to retrieve

        Returns:
            The secret value as a string

        Raises:
            VaultAccessDeniedError: If client lacks READ permission
            VaultKeyError: If the secret key doesn't exist in this vault
        """
        self._check_access(access.READ)

        with db.get_connection_context() as conn:
            secret_record = db.execute_query(
                conn,
                "SELECT value FROM vault WHERE label = %s AND key = %s",
                (self.label, key),
                fetch_one=True
            )

            if not secret_record:
                raise VaultKeyError(
                    f"Secret '{key}' not found in vault '{self.label}'."
                )
            return secret_record["value"]

    def has(self, key: str) -> bool:
        """Check if a secret exists in the vault.

        Requires READ permission. This allows clients to check for the existence
        of a secret without retrieving its value.

        Args:
            key: The secret key name to check

        Returns:
            True if the secret exists, False otherwise

        Raises:
            VaultAccessDeniedError: If client lacks READ permission
        """
        self._check_access(access.READ)

        with db.get_connection_context() as conn:
            secret_record = db.execute_query(
                conn,
                "SELECT id FROM vault WHERE label = %s AND key = %s",
                (self.label, key),
                fetch_one=True
            )
            return bool(secret_record)

    def set(self, key: str, value: str) -> None:
        """Set a secret in the vault.

        This method has smart permission checking:
        - If the key doesn't exist: Requires CREATE permission (adding new secret)
        - If the key already exists: Requires UPDATE permission (modifying existing secret)

        This allows fine-grained control where some clients can only add new secrets
        but not modify existing ones, or vice versa.

        Args:
            key: The secret key name
            value: The secret value to store

        Raises:
            VaultAccessDeniedError: If client lacks CREATE (new key) or UPDATE (existing key)

        Examples:
            # Client with CREATE permission can add new secrets
            vault.set("new_api_key", "abc123")  # Requires CREATE

            # Client with UPDATE permission can modify existing secrets  
            vault.set("existing_key", "new_value")  # Requires UPDATE

            # Client with CREATE | UPDATE can do both operations
        """
        with db.get_connection_context() as conn:
            # Check if the key already exists for this label
            existing_record = db.execute_query(
                conn,
                "SELECT id FROM vault WHERE label = %s AND key = %s",
                (self.label, key),
                fetch_one=True
            )

            if existing_record:
                # Update existing secret - requires UPDATE permission
                self._check_access(access.UPDATE)
                db.execute_query(
                    conn,
                    "UPDATE vault SET value = %s WHERE id = %s",
                    (value, existing_record["id"]),
                    fetch_one=False,
                    fetch_all=False
                )
            else:
                # Create new secret - requires CREATE permission
                self._check_access(access.CREATE)
                secret_id = uid.generate_category_uid(TABLE, length=16)
                db.execute_query(
                    conn,
                    (
                        "INSERT INTO vault (id, created_at, label, key, value)"
                        "VALUES (%s, %s, %s, %s, %s)"
                    ),
                    (secret_id, utc_time.now(), self.label, key, value),
                    fetch_one=False,
                    fetch_all=False
                )

    def delete(self, key: str) -> None:
        """Delete a secret from the vault.

        Requires DELETE permission. This is typically the most restricted permission
        since deleting secrets can break applications that depend on them.

        Args:
            key: The secret key name to delete

        Raises:
            VaultAccessDeniedError: If client lacks DELETE permission

        Note:
            If the secret doesn't exist, this method silently succeeds (no error).
            Use vault.has(key) first if you need to verify existence.
        """
        self._check_access(access.DELETE)

        with db.get_connection_context() as conn:
            db.execute_query(
                conn,
                "DELETE FROM vault WHERE label = %s AND key = %s",
                (self.label, key),
                fetch_one=False,
                fetch_all=False
            )
