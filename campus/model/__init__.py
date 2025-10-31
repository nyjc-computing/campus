"""campus.model

Models represent single entities in Campus API schema.

They are typically represented as a row in a table, or a document in a
document store.
More complex models may span multiple tables or collections.

Models are represented with dataclasses.
init parameters must be keyword-only; order of parameters should not
matter.
Models are expected to be used across the codebase; they should have
minimal dependencies, ideally none. Data processing logic should be
kept out of models.
"""

from dataclasses import dataclass, field
import typing

from campus.common import schema
from campus.common.utils import uid

from .base import Model


@dataclass(eq=False, frozen=True, kw_only=True)
class Client(Model):
    """Represents a Campus client application."""
    id: schema.CampusID = field(
        default_factory=(
            lambda: uid.generate_category_uid("client", length=8)
        )
    )
    created_at: schema.DateTime = field(
        default_factory=schema.DateTime.utcnow
    )
    name: str
    description: str
    permissions: dict[str, int] = field(default_factory=dict)


@dataclass(eq=False, frozen=True, kw_only=True)
class User(Model):
    id: schema.UserID  # type: ignore[override]
    email: schema.Email
    name: schema.String
    created_at: schema.DateTime = field(
        default_factory=schema.DateTime.utcnow
    )
    activated_at: schema.DateTime | None = None
