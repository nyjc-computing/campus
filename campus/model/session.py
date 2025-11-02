"""campus.model.session

Auth session model for the Campus API.

This module defines auth sessions for the Campus API.
"""

from dataclasses import InitVar, dataclass, field

from campus.common import schema
from campus.common.utils import uid, utc_time
import campus.config

from .base import Model


@dataclass(eq=False, kw_only=True)
class AuthSession(Model):
    """Dataclass representation of an auth session record."""
    id: schema.CampusID = field(default_factory = (
        lambda: uid.generate_category_uid("auth_session", length=16)
    ))
    # created_at inherited from BaseRecord
    expiry_seconds: InitVar[int | None] = None
    expires_at: schema.DateTime = None  # type: ignore
    client_id: schema.CampusID
    user_id: schema.UserID | None = None
    # TODO: add ip_address
    redirect_uri: schema.Url
    scopes: list[str] = field(default_factory=list)
    authorization_code: str | None = None
    state: str | None = None
    target: schema.Url | None = None

    def __post_init__(self, expiry_seconds: int | None):
        """Set expiry time based on creation timestamp.
        Cast attributes to correct types.
        """
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
