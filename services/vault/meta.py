"""services.vault.meta

Vault metadata management for the Campus vault service.
"""

from common.drum.mongodb import get_db

TABLE = "vault"


class VaultMetaAlreadyExistsError(ValueError):
    """Custom error for attempting to register an already existing vault."""
    def __init__(self, vault: str):
        super().__init__(f"Vault prefix '{vault}' already registered.")
        self.vault = vault


class VaultMetaMissingMetaDocumentError(ValueError):
    """Custom error for missing vault metadata document."""
    def __init__(self):
        super().__init__("Vault meta document not initialized.")
        self.message = "Vault meta document not initialized."


class VaultMetaMissingKeyError(KeyError):
    """Custom error for missing keys in vault metadata."""
    def __init__(self, key: str):
        super().__init__(f"Key '{key}' not found in vault metadata.")
        self.key = key


def _get_meta(key: str) -> dict:
    """Get key from vault metadata."""
    db = get_db()
    doc = db[TABLE].find_one({"@meta": True})
    if doc is None:
        raise VaultMetaMissingMetaDocumentError()
    value = db[TABLE].find_one({"@meta": True, key: {"$exists": True}})
    if value is None:
        raise VaultMetaMissingKeyError(key)
    return value

def _set_meta(key: str, value: bool) -> None:
    """Set a key-value pair in the vault metadata."""
    db = get_db()
    db[TABLE].update_one(
        {"@meta": True},
        {"$set": {key: value}},
        upsert=True
    )

def _unset_meta(key: str) -> None:
    """Unset a key in the vault metadata."""
    db = get_db()
    db[TABLE].update_one(
        {"@meta": True},
        {"$unset": {key: ""}}
    )

def deregister_vault(vault: str) -> None:
    """Deregister a vault prefix."""
    # TODO: Remove vault collection / disallow deregistering non-empty vault
    _unset_meta(f"prefix.{vault}")

def disable_vault(vault: str) -> None:
    """Disable a vault prefix."""
    _set_meta(f"prefix.{vault}", False)

def enable_vault(vault: str) -> None:
    """Enable a vault prefix."""
    _set_meta(f"prefix.{vault}", True)

def is_enabled(vault: str) -> bool:
    """Check if a vault prefix is enabled."""
    try:
        return bool(_get_meta(f"prefix.{vault}"))
    except VaultMetaMissingKeyError:
        return False  # Default to disabled if key does not exist

def meta_exists() -> bool:
    """Check if the vault metadata document exists."""
    db = get_db()
    return db[TABLE].find_one({"@meta": True}) is not None

def register_vault(prefix: str) -> None:
    """Register a new vault prefix.

    For safety, vaults are disabled upon registration.
    An existing vault cannot be registered again. An error will be raised.
    """
    try:
        _get_meta(prefix)
    except VaultMetaMissingKeyError:
        # Key does not exist, safe to register
        _set_meta(f"prefix.{prefix}", False)
    else:
        raise VaultMetaAlreadyExistsError(prefix)
