"""campus.model.credentials

Credential model definitions for Campus.
"""

from dataclasses import InitVar, dataclass, field

from campus.common import schema
from campus.common.utils import secret, utc_time

from . import constraints
from .base import Model

@dataclass(eq=False, kw_only=True)
class OAuthToken(Model):
    """Dataclass representation of a token record."""
    # access_token is stored in id
    id: str = field(default_factory=secret.generate_access_code)
    # created_at inherited from Model
    # expires_at is generated in __post_init__ if not provided
    expires_at: schema.DateTime = None  # type: ignore
    expiry_seconds: InitVar[int] = None  # type: ignore
    refresh_token: str | None = None
    refresh_token_expires_at: schema.DateTime | None = None
    scopes: list[str] = field(default_factory=list)

    def __post_init__(self, expiry_seconds: int | None = None):
        """Set expiry time based on creation timestamp."""
        if self.expires_at is None and expiry_seconds is None:
            raise ValueError(
                "Either expires_at or expiry_seconds must be provided."
            )
        if self.expires_at is None and expiry_seconds is not None:
            self.expires_at = schema.DateTime.utcafter(
                self.created_at,
                seconds=expiry_seconds
            )

    @property
    def access_token(self) -> str:
        """Convenience property; an alias for id."""
        return self.id

    @property
    def expires_in(self) -> int:
        """Get the number of seconds until the token expires."""
        created_at_dt = self.created_at.to_datetime()
        expires_at_dt = self.expires_at.to_datetime()
        assert expires_at_dt >= created_at_dt
        delta = (expires_at_dt - created_at_dt).total_seconds()
        return int(delta)

    def is_expired(self, *, at_time: schema.DateTime | None = None) -> bool:
        """Check if the token is expired at the given time (or now)."""
        at_time = at_time or schema.DateTime.utcnow()
        assert at_time
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )

    def validate_scope(self, requested_scopes: str | list[str]) -> list[str]:
        """Validate the requested scopes against the session's granted
        scopes.
        Returns the missing scopes.
        """
        if isinstance(requested_scopes, str):
            requested_scopes = requested_scopes.split(" ")
        return [
            scope for scope in self.scopes
            if scope not in requested_scopes
        ]


@dataclass(eq=False, kw_only=True)
class UserCredentials(Model):
    __constraints__ = constraints.Unique("provider", "user_id")
    id: schema.CampusID
    # created_at inherited from Model
    provider: str
    client_id: str
    user_id: schema.UserID
    # storage will hold token_id
    # user expected to set token manually after initialization
    token_id: str = field(  # type: ignore
        default=None,
        metadata={
            "storage": True,
            "resource": False,
            "constraints": constraints.UNIQUE
        }
    )
    token: OAuthToken = field(  # type: ignore
        default=None,
        init=False,
        metadata={
            "storage": False,
            "resource": True,
        }
    )

    def __post_init__(self):
        """Set token_id from token.id after initialization."""
        if self.token is not None:
            self.token_id = schema.CampusID(self.token.id)
