"""vault.model

Vault data model for managing secrets storage and retrieval.

This module contains the core Vault class that handles only database operations
without authentication or permission checking. Those concerns are handled at
the route level for better separation of responsibilities.
"""

from campus.common.utils import uid, utc_time
from . import db

TABLE = "vault"


class VaultKeyError(KeyError):
    """Custom error for when a key is not found in the vault."""

    def __init__(self, key: str, label: str):
        super().__init__(f"Key '{key}' not found in vault '{label}'.")
        self.key = key
        self.label = label


class Vault:
    """Vault data model for managing secrets in the Campus system.

    This class handles only database operations for storing and retrieving secrets.
    It does not perform authentication or permission checking - those are handled
    at the route level.

    A vault stores secrets as key-value pairs in a table.
    Each secret is stored as a separate row with label, key, and value.
    The vault is identified by a unique label.
    """

    def __init__(self, label: str):
        """Initialize a vault for the given label.
        
        Args:
            label: The vault label identifier
        """
        if not isinstance(label, str):
            raise TypeError(f"label must be a string, got {type(label).__name__}")
        self.label = label

    def __repr__(self) -> str:
        return f"Vault(label={self.label!r})"

    def get(self, key: str) -> str:
        """Get a secret from the vault.

        Args:
            key: The secret key name to retrieve

        Returns:
            The secret value as a string

        Raises:
            VaultKeyError: If the secret key doesn't exist in this vault
        """
        with db.get_connection_context() as conn:
            secret_record = db.execute_query(
                conn,
                "SELECT value FROM vault WHERE label = %s AND key = %s",
                (self.label, key),
                fetch_one=True
            )

            if not secret_record:
                raise VaultKeyError(key, self.label)
            return secret_record["value"]

    def has(self, key: str) -> bool:
        """Check if a secret exists in the vault.

        Args:
            key: The secret key name to check

        Returns:
            True if the secret exists, False otherwise
        """
        with db.get_connection_context() as conn:
            secret_record = db.execute_query(
                conn,
                "SELECT id FROM vault WHERE label = %s AND key = %s",
                (self.label, key),
                fetch_one=True
            )
            return bool(secret_record)

    def set(self, key: str, value: str) -> bool:
        """Set a secret in the vault.

        Args:
            key: The secret key name
            value: The secret value to store

        Returns:
            True if a new secret was created, False if an existing secret was updated
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
                # Update existing secret
                db.execute_query(
                    conn,
                    "UPDATE vault SET value = %s WHERE id = %s",
                    (value, existing_record["id"]),
                    fetch_one=False,
                    fetch_all=False
                )
                return False  # Updated existing
            else:
                # Create new secret
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
                return True  # Created new

    def delete(self, key: str) -> bool:
        """Delete a secret from the vault.

        Args:
            key: The secret key name to delete

        Returns:
            True if a secret was deleted, False if the key didn't exist

        Note:
            This method returns whether a deletion occurred, unlike the previous
            implementation which silently succeeded for non-existent keys.
        """
        with db.get_connection_context() as conn:
            # First check if the key exists
            existing_record = db.execute_query(
                conn,
                "SELECT id FROM vault WHERE label = %s AND key = %s",
                (self.label, key),
                fetch_one=True
            )
            
            if existing_record:
                db.execute_query(
                    conn,
                    "DELETE FROM vault WHERE label = %s AND key = %s",
                    (self.label, key),
                    fetch_one=False,
                    fetch_all=False
                )
                return True
            return False

    def list_keys(self) -> list[str]:
        """List all secret keys in this vault.

        Returns:
            List of secret key names in this vault
        """
        with db.get_connection_context() as conn:
            records = db.execute_query(
                conn,
                "SELECT key FROM vault WHERE label = %s ORDER BY key",
                (self.label,),
                fetch_one=False,
                fetch_all=True
            )
            return [record["key"] for record in records] if records else []
