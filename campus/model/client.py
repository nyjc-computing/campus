"""campus.model.client

Client model definitions for Campus.
"""

from typing import ClassVar
from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import uid

from .base import Model
from . import constraints


@dataclass(eq=False, kw_only=True)
class Client(Model):
    """Represents a Campus client application."""
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("client", length=8)
    ))
    # created_at is inherited from Model
    name: str = field(metadata={
        "constraints": [constraints.UNIQUE],
        "mutable": True,
    })
    description: str = field(metadata={"mutable": True})
    # permissions are stored in a separate table
    permissions: dict[str, int] = field(
        default_factory=dict,
        metadata={"storage": False}
    )
    # secret_hash should not be included in API responses
    secret_hash: str | None = field(
        default=None,
        repr=False,
        metadata={"resource": False}
    )


@dataclass(eq=False, kw_only=True)
class ClientAccess(Model):
    """Represents access permissions for a client to a vault label."""
    # Namespace for access constants
    READ: ClassVar[int] = 1
    CREATE: ClassVar[int] = 2
    UPDATE: ClassVar[int] = 4
    DELETE: ClassVar[int] = 8
    ALL: ClassVar[int] = READ | CREATE | UPDATE | DELETE

    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("client", length=8)
    ))
    # created_at is inherited from Model
    client_id: schema.CampusID
    label: schema.String
    # Bitflag of access permissions
    access: schema.Integer
