"""campus.model.user

User model definitions for Campus.
"""

from dataclasses import dataclass

from campus.common import schema

from .base import Model


@dataclass(eq=False, kw_only=True)
class User(Model):
    """Dataclass representation of a user record."""
    id: schema.UserID  # type: ignore
    # created_at is inherited from Model
    email: str
    name: str
    activated_at: schema.DateTime | None = None
