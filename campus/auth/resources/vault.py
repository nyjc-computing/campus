"""campus.auth.vault

Implements Campus API for vault access.
"""

from campus.common import schema
from campus.common.utils import uid
import campus.model
import campus.storage

vault_storage = campus.storage.get_table("vault")


class VaultsResource:
    """Represents the vaults resource in Campus API Schema."""

    def __getitem__(self, label: str) -> "VaultResource":
        """Get a vault by label.

        Args:
            label: The vault label

        Returns:
            VaultResource instance
        """
        return VaultResource(label)

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for vault resource."""
        vault_storage.init_from_model("vault", campus.model.Vault)


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
        rows = vault_storage.get_matching({"key": key, "label": self.label})
        # breakpoint()
        if not rows:
            vault_storage.insert_one({
                "id": uid.generate_category_uid("vault"),
                "created_at": schema.DateTime.utcnow(),
                "label": self.label,
                "key": key,
                "value": value
            })
        else:
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
