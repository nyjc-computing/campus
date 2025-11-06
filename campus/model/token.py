"""campus.model.token

Token model for the Campus API.

This module defines OAuth2 access tokens for the Campus API.
"""

from dataclasses import InitVar, dataclass, field

from campus.common import schema
from campus.common.utils import secret, utc_time

from .base import Model


@dataclass(eq=False, kw_only=True)
class Token(Model):
    """Dataclass representation of an OAuth2 access token."""
    id: schema.CampusID = field(default_factory=secret.generate_access_code)
    # created_at inherited from Model
    expiry_seconds: InitVar[int | None] = None
    expires_at: schema.DateTime = None  # type: ignore
    client_id: schema.CampusID
    user_id: schema.UserID
    scopes: list[str] = field(default_factory=list)

    def __post_init__(self, expiry_seconds: int | None):
        """Set expiry time based on creation timestamp."""
        if expiry_seconds is not None and self.expires_at is None:
            self.expires_at = schema.DateTime.utcafter(
                self.created_at,
                seconds=expiry_seconds
            )

    @property
    def access_token(self) -> str:
        """Convenience property that makes access_token an alias for id."""
        return self.id

    @property
    def expires_in(self) -> int:
        """Get the number of seconds until the token expires."""
        created_at_dt = self.created_at.to_datetime()
        expires_at_dt = self.expires_at.to_datetime()
        assert expires_at_dt >= created_at_dt
        delta = (expires_at_dt - created_at_dt).total_seconds()
        return int(delta)

    def is_expired(self, at_time: schema.DateTime | None = None) -> bool:
        """Check if the token is expired at the given time (or now)."""
        at_time = at_time or schema.DateTime.utcnow()
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )
