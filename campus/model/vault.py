"""campus.model.vault

Vault model definitions for Campus.
"""

from dataclasses import dataclass

from campus.common import schema

from .base import Model


@dataclass(eq=False, kw_only=True)
class Vault(Model):
    """Dataclass representation of a vault record."""
    id: schema.CampusID  # type: ignore
    # created_at is inherited from Model
    label: str
    key: str
    value: str
