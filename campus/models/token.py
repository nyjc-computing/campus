"""campus.models.token

JWT Token model for OAuth2 providers.

Tokens are issued for:
- a specific Campus client (by client_id)
- a specific Campus user (by user_id)
- specific scopes

Tokens follow storage interface requirements and will have
`id` and `created_at` fields.

Tokens are long-lived and may persist over multiple days.
"""

from dataclasses import InitVar, dataclass, field
from typing import Any, Literal, TypedDict, overload

from campus.common import devops, schema
from campus.common.errors import api_errors
from campus.common.utils import secret, utc_time
from campus.models.base import BaseRecord, BaseRecordDict
from campus.storage import (
    errors as storage_errors,
    get_table
)

TABLE = "tokens"
DEFAULT_EXPIRY_SECONDS = utc_time.DAY_SECONDS * 30  # 30 days


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the tables needed by the model.

    This function is intended to be called only in a test environment (using a
    local-only db like SQLite), or in a staging environment before upgrading to
    production.
    """
    storage = get_table(TABLE)
    table_schema = f"""
        CREATE TABLE IF NOT EXISTS "{TABLE}" (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            expires_at TEXT,
            client_id TEXT,
            user_id TEXT,
            scopes TEXT,
            UNIQUE(client_id, user_id)
        )
    """
    storage.init_table(table_schema)


class TokenRecordDict(BaseRecordDict):
    """Schema for a full token record."""
    expires_at: schema.DateTime
    client_id: schema.CampusID
    user_id: schema.UserID
    scopes: str


class TokenNew(TypedDict):
    """Schema for a new token request."""
    client_id: schema.CampusID
    user_id: schema.UserID
    scopes: list[str]




@dataclass(eq=False, kw_only=True)
class SanitizedTokenRecord:
    """Dataclass representation of a sanitized token record.

    This is used to return token information without sensitive fields.
    """
    client_id: schema.CampusID
    user_id: schema.UserID
    scopes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SanitizedTokenRecord":
        """Create a SanitizedTokenRecord from a dictionary.
        
        Scopes are stored as space-separated strings in the database,
        but as a list in the dataclass.
        """
        token_data = dict(data)  # Make a copy to avoid mutating input
        if isinstance(token_data["scopes"], str):
            token_data["scopes"] = token_data["scopes"].split(" ")
        return cls(**token_data)

    def get_missing_scopes(self, scopes: str | list[str]) -> list[str]:
        """Validate the requested scopes against the session's granted scopes.
        Returns the missing scopes.
        """
        if isinstance(scopes, str):
            scopes = scopes.split(" ")
        return [
            scope for scope in scopes
            if scope not in self.scopes
        ]


@dataclass(eq=False, kw_only=True)
class TokenRecord(BaseRecord):
    """Dataclass representation of a token record."""
    # access_token is stored in id
    id: str = field(default_factory=secret.generate_access_code)
    # expires_at is generated in __post_init__ if not provided
    expires_at: schema.DateTime = None  # type: ignore
    expiry_seconds: InitVar[int] = DEFAULT_EXPIRY_SECONDS
    client_id: schema.CampusID
    user_id: schema.UserID
    refresh_token: str | None = None
    scopes: list[str] = field(default_factory=list)

    def __post_init__(self, expiry_seconds: int):
        """Set expiry time based on creation timestamp."""
        if self.expires_at is None:
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

    @classmethod
    def from_dict(cls, data: dict) -> "TokenRecord":
        """Create a TokenRecord from a dictionary.
        
        The dictionary is expected to be obtained from a token endpoint.
        Scopes are stored as space-separated strings in the database,
        but as a list in the dataclass.
        """
        token_data = dict(data)  # Make a copy to avoid mutating input
        if isinstance(token_data["scope"], str):
            token_data["scopes"] = token_data["scope"].split(" ")
        if "access_token" in token_data:
            token_data["id"] = token_data.pop("access_token")
        if "token_type" in token_data:
            token_data.pop("token_type")  # Ignore token_type if present
        return super().from_dict(token_data)

    def is_expired(self, *, at_time: schema.DateTime | None = None) -> bool:
        """Check if the token is expired at the given time (or now)."""
        at_time = at_time or schema.DateTime.utcnow()
        return utc_time.is_expired(
            self.expires_at.to_datetime(),
            at_time=at_time.to_datetime()
        )

    def sanitized(self) -> SanitizedTokenRecord:
        """Return a sanitized version of the token record."""
        return SanitizedTokenRecord(
            client_id=self.client_id,
            user_id=self.user_id,
            scopes=self.scopes
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the TokenRecord to a dictionary.

        Scopes are stored as space-separated strings in the database,
        but as a list in the dataclass.
        """
        data = super().to_dict()
        data["token_type"] = "Bearer"
        data["scopes"] = " ".join(self.scopes)
        data["access_token"] = data.pop("id")
        return data

    def validate_scope(self, scopes: str | list[str]) -> list[str]:
        """Validate the requested scopes against the session's granted scopes.
        Returns the missing scopes.
        """
        if isinstance(scopes, str):
            scopes = scopes.split(" ")
        return [
            scope for scope in scopes
            if scope not in self.scopes
        ]


class Tokens:
    """Token model for handling database operations related to tokens."""

    def __init__(self):
        """Initialize the Token model with a table storage interface."""
        self.storage = get_table(TABLE)

    def delete(self, token_id: schema.CampusID) -> None:
        """Delete a token from the database."""
        self.storage.delete_by_id(token_id)

    @overload
    def find(self, sanitized: Literal[True], **match: str) -> list[SanitizedTokenRecord]: ...
    @overload
    def find(self, sanitized: Literal[False], **match: str) -> list[TokenRecord]: ...
    def find(self, sanitized: bool = True, **match: str):
        """Retrieve a list of matching tokens. 

        This is intended for session retrieval by user and/or client, 
        and not meant for authentication. 
        For security reasons, the token id, access_token and expiry
        are stripped by default. Pass `sanitized=False` to get full records.
        """
        if schema.CAMPUS_KEY in match:
            raise ValueError(
                "'id=' keyword argument in find() by id is not allowed.\n"
                "use get() instead."
            )
        if sanitized:
            tokens = [
                SanitizedTokenRecord.from_dict(token)
                for token in self.storage.get_matching(match)
            ]
        else:
            tokens = [
                TokenRecord.from_dict(token)
                for token in self.storage.get_matching(match)
            ]
        return tokens

    def get_by_client_user(self, client_id: str, user_id: str) -> TokenRecord:
        """Get the token for a client/user pair. Returns None if not found."""
        results = self.find(sanitized=False, client_id=client_id, user_id=user_id)
        if len(results) == 0:
            raise api_errors.NotFoundError(
                message="Token not found for this client and user",
                client_id=client_id,
                user_id=user_id
            )
        elif len(results) > 1:
            raise api_errors.InternalError(
                message="Multiple tokens found for this client and user",
                client_id=client_id,
                user_id=user_id
            )
        token = results[0]
        assert isinstance(token, TokenRecord)
        return token

    def get(self, token_id: schema.CampusID) -> TokenRecord:
        """Retrieve a token from the database by its ID."""
        token_record = self.storage.get_by_id(token_id)
        token = TokenRecord.from_dict(token_record)
        return token

    def new(
            self,
            *,
            client_id: schema.CampusID,
            user_id: schema.UserID,
            scopes: list[str],
            expiry_seconds: int = DEFAULT_EXPIRY_SECONDS
    ) -> TokenRecord:
        """Create a new token in the database."""
        token = TokenRecord(
            client_id=client_id,
            user_id=user_id,
            scopes=scopes,
        )
        try:
            self.storage.insert_one(token.to_dict())
        except storage_errors.ConflictError:
            raise api_errors.ConflictError(
                message="Token already exists for this user and client",
                client_id=token.client_id,
                user_id=token.user_id
            ) from None
        return token

    def sweep(
            self,
            *, 
            at_time: schema.DateTime | None = None
    ) -> int:
        """Delete expired tokens from the database.

        Returns the number of deleted tokens.
        """
        at_time = at_time or schema.DateTime.utcnow()
        all_tokens = self.find(sanitized=False)
        expired_token_ids = [
            token.id for token in all_tokens
            if token.is_expired(at_time=at_time)
        ]
        # TODO: Optimize to do this in a single query
        for token_id in expired_token_ids:
            self.delete(token_id)
        return len(expired_token_ids)

    def update(self, token: TokenRecord) -> None:
        """Update an existing token in the database."""
        self.storage.update_by_id(token.id, token.to_dict())
