"""services.vault

Vault service for managing secrets and sensitive system data in Campus.

Each vault (in a collection) is identified by a unique label.
Client access to vault labels is controlled through client permissions.
Clients are identified by the CLIENT_ID environment variable.
"""

import os
from storage import get_table

TABLE = "vault"
ACCESS_TABLE = "vault_access"

__all__ = [
    "get_vault",
    "Vault",
    "VaultAccessDeniedError",
    "VaultKeyError",
    "init_db",
    "grant_access",
    "revoke_access",
    "has_access",
]


def get_vault(label: str) -> "Vault":
    """Get a Vault instance by label using the CLIENT_ID environment variable."""
    if not isinstance(label, str):
        raise TypeError(f"label must be a string, got {type(label).__name__}")
    return Vault(label)


def grant_access(client_id: str, label: str) -> None:
    """Grant a client access to a vault label."""
    access_storage = get_table(ACCESS_TABLE)
    
    # Check if access already exists
    existing_access = access_storage.get_matching({"client_id": client_id, "label": label})
    if not existing_access:
        from common.utils import uid, utc_time
        access_id = uid.generate_category_uid(ACCESS_TABLE, length=16)
        access_record = {
            "id": access_id,
            "created_at": utc_time.now(),
            "client_id": client_id,
            "label": label
        }
        access_storage.insert_one(access_record)


def revoke_access(client_id: str, label: str) -> None:
    """Revoke a client's access to a vault label."""
    access_storage = get_table(ACCESS_TABLE)
    access_records = access_storage.get_matching({"client_id": client_id, "label": label})
    for record in access_records:
        access_storage.delete_by_id(record["id"])


def has_access(client_id: str, label: str) -> bool:
    """Check if a client has access to a vault label."""
    access_storage = get_table(ACCESS_TABLE)
    access_records = access_storage.get_matching({"client_id": client_id, "label": label})
    return bool(access_records)


def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    """
    vault_storage = get_table(TABLE)
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
    vault_storage.init_table(vault_schema)
    
    access_storage = get_table(ACCESS_TABLE)
    access_schema = """
        CREATE TABLE IF NOT EXISTS vault_access (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            client_id TEXT NOT NULL,
            label TEXT NOT NULL,
            UNIQUE(client_id, label)
        )
    """
    access_storage.init_table(access_schema)


class VaultAccessDeniedError(ValueError):
    """Custom error for when a client doesn't have access to a vault label."""

    def __init__(self, client_id: str, label: str):
        super().__init__(f"Client '{client_id}' does not have access to vault label '{label}'.")
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
    Client identity is determined by the CLIENT_ID environment variable.
    """

    def __init__(self, label: str):
        self.label = label
        client_id = os.environ.get("CLIENT_ID")
        if not client_id:
            raise ValueError("CLIENT_ID environment variable is required")
        self.client_id = client_id
        self.storage = get_table(TABLE)

    def __repr__(self) -> str:
        return f"Vault(label={self.label!r})"

    def _check_access(self) -> None:
        """Check if the client has access to this vault label."""
        if not has_access(self.client_id, self.label):
            raise VaultAccessDeniedError(self.client_id, self.label)

    def get(self, key: str) -> str:
        """Get a secret from the vault."""
        self._check_access()
        
        secret_records = self.storage.get_matching({"label": self.label, "key": key})
        if not secret_records:
            raise VaultKeyError(
                f"Secret '{key}' not found in vault '{self.label}'."
            )
        return secret_records[0]["value"]

    def has(self, key: str) -> bool:
        """Check if a secret exists in the vault."""
        self._check_access()
        
        secret_records = self.storage.get_matching({"label": self.label, "key": key})
        return bool(secret_records)

    def set(self, key: str, value: str) -> None:
        """Set a secret in the vault."""
        self._check_access()
        
        # Check if the key already exists for this label
        existing_records = self.storage.get_matching({"label": self.label, "key": key})
        if existing_records:
            # Update existing secret
            record_id = existing_records[0]["id"]
            self.storage.update_by_id(record_id, {"value": value})
        else:
            # Create new secret
            from common.utils import uid, utc_time
            secret_id = uid.generate_category_uid(TABLE, length=16)
            new_secret = {
                "id": secret_id,
                "created_at": utc_time.now(),
                "label": self.label,
                "key": key,
                "value": value
            }
            self.storage.insert_one(new_secret)

    def delete(self, key: str) -> None:
        """Delete a secret from the vault."""
        self._check_access()
        
        secret_records = self.storage.get_matching({"label": self.label, "key": key})
        if secret_records:
            record_id = secret_records[0]["id"]
            self.storage.delete_by_id(record_id)
