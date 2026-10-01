"""campus.model.client

Client model definitions for Campus.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from campus.common import schema
from campus.common.utils import uid

from . import constraints
from .base import Model


@dataclass(eq=False, kw_only=True)
class Client(Model):
    """Represents a Campus client application.

    Clients can be either:
    - Confidential: Have a client_secret and can securely store credentials
    - Public: No client_secret (CLI, mobile apps, native applications)

    Per RFC 6749 Section 2.1:
    "Public clients are client applications incapable of keeping the
    client password confidential."
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("client", length=8)
    ))
    # created_at is inherited from Model
    name: str = field(metadata={
        "constraints": [constraints.UNIQUE],
        "mutable": True,
    })
    description: str = field(metadata={"mutable": True})
    # Mark public clients (no secret required) - CLI, mobile apps, native applications
    is_public: bool = field(
        default=False,
        metadata={"mutable": False}
    )
    # OAuth redirect URIs for public clients (e.g. "urn:ietf:wg:oauth:2.0:oob")
    redirect_uris: list[str] = field(
        default_factory=list,
        metadata={"mutable": True}
    )
    # Scopes this client may be granted on Campus tokens. Fail-closed:
    # an empty allowlist grants nothing, so scope-bearing sessions and
    # device codes are rejected until the client's registered scopes
    # are set (docs/auth-token-invariants.md A1).
    allowed_scopes: list[str] = field(
        default_factory=list,
        metadata={"mutable": True}
    )
    # Upstream (third-party provider) scopes the client may be granted
    # through Campus's OAuth proxies, keyed by provider name. Fail-closed:
    # an absent provider entry means the client may only receive that
    # proxy's base scopes (docs/auth-token-invariants.md B3).
    upstream_scopes: dict[str, list[str]] = field(
        default_factory=dict,
        metadata={"mutable": True}
    )
    # permissions are stored in a separate table
    permissions: dict[str, int] = field(
        default_factory=dict,
        metadata={"storage": False}
    )
    # secret_hash should not be included in API responses
    # For public clients, this is None
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
