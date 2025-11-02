"""campus.auth.vault

Implements Campus API for vault access.
"""

__all__ = ['get']

import campus.storage

vault_storage = campus.storage.get_table("vault")


def get(label: str) -> "VaultResource":
    """Get the Vault service client.

    Args:
        label: The vault label to access
        permission: The required permission bitflag for access
    """
    return VaultResource(label)


class VaultsResource:
    """Represents the vaults resource in Campus API Schema."""

    def __getitem__(self, label: str) -> "VaultResource":
        """Get a vault by label.

        Args:
            label: The vault label

        Returns:
            VaultResource instance
        """
        return get(label)


class VaultResource:
    """Represents a single vault, a collection of vault keys."""

    def __init__(self, label: str):
        self.label = label

    def __delitem__(self, key: str) -> None:
        """Delete a vault item by key.

        Args:
            key: The vault key (e.g., "apps", "storage", "oauth")
        """
        vault_storage.delete_matching({"key": key, "label": self.label})

    def __getitem__(self, key: str) -> str:
        """Get a vault item by key.

        Args:
            key: The vault key (e.g., "apps", "storage", "oauth")
        """
        rec = vault_storage.get_matching(
            {"key": key, "label": self.label}
        )
        if rec is None:
            raise KeyError(f"{key!r} not found in {self.label!r}")
        assert len(rec) == 1
        return rec[0]["value"]

    def __setitem__(self, key: str, value: str) -> None:
        """Set a vault item by key.

        Args:
            key: The vault key (e.g., "apps", "storage", "oauth")
            value: The secret value to store
        """
        vault_storage.update_matching(
            {"key": key, "label": self.label},
            {"value": value}
        )

    def keys(self) -> list[str]:
        """List available vault keys.

        Returns:
            List of available vault keys
        """
        records = vault_storage.get_matching({"label": self.label})
        return [rec["key"] for rec in records]
