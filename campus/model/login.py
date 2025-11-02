"""campus.model.login

Login session model for the Campus API.

This module defines login sessions for the Campus API.
"""

from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import utc_time
import campus.config

from .base import Model


@dataclass(eq=False, kw_only=True)
class LoginSession(Model):
    """Dataclass representation of a login session record."""
    # id and created_at inherited from BaseRecord
    expires_at: schema.DateTime = None  # type: ignore
    client_id: schema.CampusID
    user_id: schema.UserID | None = None
    device_id: str | None = None
    # TODO: add ip_address
    # TODO: add last_login?
    agent_string: str

    def __post_init__(self):
        """Set expiry time based on creation timestamp."""
        if self.expires_at is None:
            self.expires_at = schema.DateTime.utcafter(
                self.created_at,
                seconds=(
                    campus.config.DEFAULT_LOGIN_EXPIRY_DAYS
                    * utc_time.DAY_SECONDS
                )
            )

    def is_expired(self, at_time: schema.DateTime | None = None) -> bool:
        """Check if the session is expired."""
        if at_time is None:
            at_time = schema.DateTime.utcnow()
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )
