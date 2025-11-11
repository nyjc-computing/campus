"""campus.model.login

Login session model for the Campus API.

This module defines login sessions for the Campus API.
"""

from dataclasses import InitVar, dataclass, field

from campus.common import schema
from campus.common.utils import uid, utc_time

from .base import Model


@dataclass(eq=False, kw_only=True)
class LoginSession(Model):
    """Dataclass representation of a login session record."""
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("login_session", length=16)
    ))
    # created_at inherited from BaseRecord
    expiry_seconds: InitVar[int | None] = None
    expires_at: schema.DateTime = None  # type: ignore
    client_id: schema.CampusID
    user_id: schema.UserID | None
    device_id: str | None = None
    # TODO: add ip_address
    # TODO: add last_login?
    agent_string: str

    def __post_init__(self, expiry_seconds: int | None):
        """Set expiry time based on creation timestamp."""
        if expiry_seconds is not None and self.expires_at is None:
            self.expires_at = schema.DateTime.utcafter(
                self.created_at,
                seconds=expiry_seconds
            )

    def is_expired(self, at_time: schema.DateTime | None = None) -> bool:
        """Check if the session is expired."""
        if at_time is None:
            at_time = schema.DateTime.utcnow()
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )
