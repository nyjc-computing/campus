"""campus.model.device_code

Device code model for OAuth 2.0 Device Authorization Flow (RFC 8628).

This module defines the device code model for tracking pending
device authorization requests.
"""

from dataclasses import InitVar, dataclass, field

from campus.common import schema
from campus.common.utils import uid, utc_time

from .base import Model


@dataclass(eq=False, kw_only=True)
class DeviceCode(Model):
    """Dataclass representation of a device code record.

    Device codes are used in the OAuth 2.0 Device Authorization Flow
    to track authorization requests from CLI or other devices with
    limited input capabilities.

    Reference: https://datatracker.ietf.org/doc/html/rfc8628
    """
    id: schema.CampusID = field(default_factory = (
        lambda: uid.generate_category_uid("device_code", length=16)
    ))
    # The device code - used by the client for polling
    device_code: str
    # The user code - entered by the user on the verification page
    user_code: str
    # Client identifier
    client_id: schema.CampusID
    # When the user has authenticated, their user_id is stored here
    user_id: schema.UserID | None = None
    # OAuth scopes requested
    scopes: list[str] = field(default_factory=list)
    # Expiry timestamp
    expiry_seconds: InitVar[int | None] = None
    expires_at: schema.DateTime = None  # type: ignore
    # Minimum seconds between polling attempts
    interval: int = 5
    # Current state of the authorization flow
    state: str = "pending"  # pending, authorized, denied, expired

    def __post_init__(self, expiry_seconds: int | None):
        """Set expiry time based on creation timestamp."""
        if expiry_seconds is not None and self.expires_at is None:
            self.expires_at = schema.DateTime.utcafter(
                self.created_at,
                seconds=expiry_seconds
            )

    def is_expired(self, at_time: schema.DateTime | None = None) -> bool:
        """Check if the device code is expired."""
        if at_time is None:
            at_time = schema.DateTime.utcnow()
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )

    def can_poll(self, at_time: schema.DateTime | None = None) -> bool:
        """Check if the device code is still valid for polling."""
        if self.is_expired(at_time):
            return False
        return self.state in ("pending", "authorized")

    def authorize(self, user_id: schema.UserID) -> None:
        """Mark the device code as authorized by the given user."""
        self.user_id = user_id
        self.state = "authorized"

    def deny(self) -> None:
        """Mark the device code as denied by the user."""
        self.state = "denied"

    def expire(self) -> None:
        """Mark the device code as expired."""
        self.state = "expired"
