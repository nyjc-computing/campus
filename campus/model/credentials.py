"""campus.model.credentials

Credential model definitions for Campus.
"""

import typing
from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import secret, utc_time

from . import constraints
from .base import Model

# Token types are case-insensitive per RFC 6749 section 7.1; the
# canonical campus spelling is the RFC 6750 "Bearer" designation.
_BEARER_TOKEN_TYPE = "Bearer"


def _as_datetime(value: schema.DateTime | str) -> schema.DateTime:
    """Coerce a string value to schema.DateTime.

    Resources and storage records carry datetimes as plain strings;
    model code expects schema.DateTime.
    """
    if isinstance(value, schema.DateTime):
        return value
    return schema.DateTime(str(value))


@dataclass(eq=False, kw_only=True)
class OAuthToken(Model):
    """Dataclass representation of a token record.

    Presents an RFC 6749-compliant interface (with RFC 6750 bearer
    usage) while storage follows campus semantics (mandatory id):

    - id is the token string; access_token is a read-only alias.
    - expires_in is the token lifetime in seconds at issuance
      (RFC 6749 section 4.2.2); expires_at is derived as
      created_at + expires_in and is the temporal authority.
    - scope (space-delimited string) and scopes (list) are views of
      the same granted scopes; storage keeps the scope string (#648
      end state).
    - token_type defaults to "Bearer" and is case-normalised on
      input; only Bearer tokens are treated as usable.
    - provider_fields reserves a home for unknown keys accepted from
      provider token payloads (e.g. Google id_token); stored for
      internal use but not emitted in resources.

    from_resource() accepts both standard and campus key names.

    See issue #648.
    """
    # access_token is stored in id
    id: str = field(default_factory=secret.generate_access_code)  # type: ignore[assignment]
    # created_at inherited from Model
    # expires_at is derived from expires_in in __post_init__ if not provided
    expires_at: schema.DateTime = None  # type: ignore
    expires_in: int | None = None
    token_type: str = _BEARER_TOKEN_TYPE
    refresh_token: str | None = None
    refresh_token_expires_at: schema.DateTime | None = None
    scopes: list[str] = field(default_factory=list)
    provider_fields: dict[str, typing.Any] = field(
        default_factory=dict,
        metadata={
            "storage": True,
            "resource": False,
        }
    )

    def __post_init__(self):
        """Resolve expiry fields and normalise token_type and scopes."""
        if isinstance(self.scopes, str):
            self.scopes = self.scopes.split()
        if self.expires_at is None:
            if self.expires_in is None:
                raise ValueError(
                    "Either expires_at or expires_in must be provided."
                )
            self.expires_at = schema.DateTime.utcafter(
                _as_datetime(self.created_at),
                seconds=self.expires_in
            )
        expires_at = _as_datetime(self.expires_at)
        created_at = _as_datetime(self.created_at)
        # expires_at is the temporal authority; keep the stored
        # invariant expires_at = created_at + expires_in
        self.expires_at = expires_at
        self.expires_in = int(
            (expires_at.to_datetime() - created_at.to_datetime()).total_seconds()
        )
        if not self.token_type or self.token_type.lower() == _BEARER_TOKEN_TYPE.lower():
            self.token_type = _BEARER_TOKEN_TYPE

    @property
    def access_token(self) -> str:
        """Convenience property; an alias for id."""
        return self.id

    @property
    def scope(self) -> str:
        """Convenience property; RFC 6749 space-delimited scope string."""
        return " ".join(self.scopes)

    @scope.setter
    def scope(self, value: str | list[str]) -> None:
        """Set the granted scopes from a scope string or list."""
        if isinstance(value, str):
            self.scopes = value.split()
        else:
            self.scopes = list(value)

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

    @classmethod
    def from_resource(cls, resource: dict) -> "OAuthToken":
        """Create an OAuthToken from a resource dict.

        Accepts RFC 6749 standard keys alongside campus keys:
        access_token maps to id and scope to scopes. Unknown keys are
        preserved in provider_fields for internal use (issue #648).
        """
        processed = dict(resource)
        if "access_token" in processed:
            processed.setdefault("id", processed.pop("access_token"))
        if "scope" in processed:
            processed.setdefault("scopes", processed.pop("scope"))
        expires_in = processed.get("expires_in")
        if isinstance(expires_in, str):
            processed["expires_in"] = int(expires_in)
        known_keys = cls.fields().keys()
        provider_fields = {
            key: processed.pop(key)
            for key in list(processed)
            if key not in known_keys
        }
        if provider_fields:
            processed.setdefault("provider_fields", {})
            processed["provider_fields"].update(provider_fields)
        token = super().from_resource(processed)
        # provider_fields is not a resource field, so base.from_resource
        # skips it; assign the collected extras after construction
        token.provider_fields = processed.get("provider_fields", {})
        return token

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert the token to a resource dict.

        Emits the RFC 6749 scope string only (the scopes list alias was
        dropped from resources when the #648 deprecation window closed
        on the emission side); the scopes field remains on the model
        and from_resource still accepts both keys.
        """
        resource = super().to_resource()
        resource.pop("scopes", None)
        resource["scope"] = self.scope
        return resource

    @classmethod
    def from_storage(cls, record: dict) -> "OAuthToken":
        """Create OAuthToken from storage record, properly deserializing DateTime fields.

        Storage records carry the RFC 6749 scope string (issue #648
        end state); the legacy scopes list is still accepted on read
        for tolerance. Records written before #648 carry no expires_in,
        token_type, or provider_fields; the missing values are derived
        from expires_at or defaulted (the migrations/005 backfill
        removes the need for this, but reads stay tolerant).

        Args:
            record: Storage record dictionary

        Returns:
            OAuthToken instance with DateTime fields properly deserialized
        """
        # Convert string datetime values to schema.DateTime objects
        processed = record.copy()
        if "scope" in processed and "scopes" not in processed:
            processed["scopes"] = str(processed["scope"]).split()
        if "expires_at" in processed and isinstance(processed["expires_at"], str):
            processed["expires_at"] = schema.DateTime(processed["expires_at"])
        if "refresh_token_expires_at" in processed and isinstance(processed["refresh_token_expires_at"], str):
            processed["refresh_token_expires_at"] = schema.DateTime(processed["refresh_token_expires_at"])
        if "created_at" in processed and isinstance(processed["created_at"], str):
            processed["created_at"] = schema.DateTime(processed["created_at"])
        return super().from_storage(processed)

    def to_storage(self) -> dict[str, typing.Any]:
        """Convert the token to a storage record.

        Storage keeps the RFC 6749 scope string per the #648 end state
        (decision 4); the scopes list is a model-side convenience only.
        """
        record = super().to_storage()
        record.pop("scopes", None)
        record["scope"] = self.scope
        return record


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
            "constraints": [constraints.UNIQUE]
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

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert the credentials to a resource dict.

        The joined token is serialized by OAuthToken.to_resource()
        rather than left as a dataclass for the JSON layer's default
        asdict() handling: asdict() skips the token's scope property
        and would leak provider_fields into the response (issue
        #648 decision 4/5; gap found during #650 dev verification).
        """
        resource = super().to_resource()
        if self.token is not None:
            resource["token"] = self.token.to_resource()
        return resource


@dataclass(eq=False, kw_only=True)
class AppCredentials(Model):
    """Client-scoped credentials for the client_credentials grant
    (RFC 6749 section 4.4).

    The confidential client itself is the resource owner, so unlike
    UserCredentials these link a client to its single live app token
    with no user involved: bearer authentication resolves the token to
    the client alone. App tokens never carry a refresh token (RFC 6749
    section 4.4.3).
    """
    __constraints__ = constraints.Unique("client_id")
    id: schema.CampusID
    # created_at inherited from Model
    client_id: str
    # storage will hold token_id
    # caller expected to set token manually after initialization
    token_id: str = field(  # type: ignore
        default=None,
        metadata={
            "storage": True,
            "resource": False,
            "constraints": [constraints.UNIQUE]
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

    def to_resource(self) -> dict[str, typing.Any]:
        """Convert the credentials to a resource dict.

        The joined token is serialized by OAuthToken.to_resource() for
        the same reasons as UserCredentials (issue #648).
        """
        resource = super().to_resource()
        if self.token is not None:
            resource["token"] = self.token.to_resource()
        return resource
