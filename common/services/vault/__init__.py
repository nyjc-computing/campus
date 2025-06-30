"""common.services.vault

Vault service for managing secrets and sensitive system data in Campus.

Each vault (in a collection) is identified by a unique label.
To avoid collision between label and keys in the vault, the label key is prefixed with '@', i.e. '@label'.
"""

from common.drum.mongodb import PK, get_db, get_drum

from . import meta

PREFIX = "@"
TABLE = "vault"


def prefixed(value: "Prefixable") -> str:
    """Create a prefixed string."""
    if not isinstance(value, Prefixable):
        raise TypeError(
            f"prefixed() expects Prefixed instance, got {type(value).__name__}"
        )
    return value.__prefixed__()


class Prefixable(str):
    """String with a prefix."""
    def __new__(cls, value: str, prefix: str = PREFIX):
        if value.startswith(prefix):
            raise ValueError(
                f"Value '{value}' already starts with prefix '{prefix}'"
            )
        return super().__new__(cls, value)
    
    def __prefixed__(self) -> str:
        """Return the prefixed string.

        This is not a built-in dunder method, but a custom method
        """
        return PREFIX + super().__str__()

    def __repr__(self) -> str:
        return f"Prefixed('{super().__str__().lstrip(PREFIX)}')"


def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    # Check for existing vault metadata document
    if not meta.meta_exists():
        db = get_db()
        # Create the vault metadata collection if it does not exist
        db[TABLE].insert_one({"@meta": True})


class VaultDisabledOrNotFoundError(ValueError):
    """Custom error for when a vault is disabled or not found."""
    def __init__(self, label: str):
        super().__init__(f"Vault '{label}' is disabled or not found.")
        self.label = label


class VaultKeyError(KeyError):
    """Custom error for when a key is not found in the vault."""
    def __init__(self, key: str):
        super().__init__(f"Key '{key}' not found in vault.")
        self.key = key


class Vault:
    """Vault model for managing secrets in the Campus system.
    
    A vault is a collection of secrets represented in a document.
    Each secret is stored as a key-value pair in the vault document.
    The vault is recognised by a unique label.
    """
    def __init__(self, label: str):
        self.label = label

    def get(self, key: str) -> str:
        """Get a secret from the vault."""
        if not meta.is_enabled(self.label):
            raise VaultDisabledOrNotFoundError(self.label)
        db = get_db()
        vault = db[TABLE].find_one({"@label": self.label})
        if vault is None:
            raise VaultDisabledOrNotFoundError(self.label)
        if key not in vault:
            raise VaultKeyError(
                f"Secret '{key}' not found in vault '{self.label}'."
            )
        return vault[key]

    def set(self, key: str, value: str) -> None:
        """Set a secret in the vault."""
        if not meta.is_enabled(self.label):
            raise VaultDisabledOrNotFoundError(self.label)
        db = get_db()
        db[TABLE].update_one(
            {"@label": self.label},
            {"$set": {key: value}},
            upsert=True
        )
    
    def delete(self, key: str) -> None:
        """Delete a secret from the vault."""
        if not meta.is_enabled(self.label):
            raise VaultDisabledOrNotFoundError(self.label)
        db = get_db()
        db[TABLE].update_one(
            {"@label": self.label},
            {"$unset": {key: ""}}
        )
