"""campus.models.token

(Bearer) Token model for the Campus API.

Tokens are issued for:
- a specific Campus client (by client_id)
- a specific Campus user (by user_id)
- specific scopes

Tokens follow storage interface requirements and will have
`id` and `created_at` fields.

Tokens are long-lived and may persist over multiple days.
"""

from typing import TypedDict

from campus.common import devops, schema
from campus.common.errors import api_errors
from campus.common.utils import secret, uid, utc_time
from campus.models.base import BaseRecordDict
from campus.storage import (
    errors as storage_errors,
    get_table
)

TABLE = "tokens"


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
            agent_string TEXT,
            access_token TEXT,
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


class Tokens:
    """Token model for handling database operations related to tokens."""

    def __init__(self):
        """Initialize the Token model with a table storage interface."""
        self.storage = get_table(TABLE)

    @staticmethod
    def _sanitize_token(token: dict[str, str]) -> dict[str, str]:
        """Remove sensitive fields from a token record before returning it."""
        sanitized = dict(token)
        del sanitized[schema.CAMPUS_KEY]
        del sanitized["access_token"]
        del sanitized["expires_at"]
        return sanitized

    def delete(self, token_id: schema.CampusID) -> None:
        """Delete a token from the database."""
        self.storage.delete_by_id(token_id)

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
        tokens = self.storage.get_matching(match)
        return tokens

    def get(self, token_id: schema.CampusID) -> TokenRecordDict:
        """Retrieve a token from the database by its ID."""
        token_record = self.storage.get_by_id(token_id)
        return token

    def new(
            self,
            token_data: TokenNew,
            *,
            expiry_seconds: int = DEFAULT_EXPIRY_SECONDS
    ) -> TokenRecordDict:
        """Create a new token in the database."""
        token = dict(token_data)
        token[schema.CAMPUS_KEY] = uid.generate_category_uid("token")
        now = schema.DateTime.utcnow()
        token["created_at"] = now
        token["expires_at"] = schema.DateTime.utcafter(
            now, seconds=expiry_seconds
        )
        token["access_token"] = secret.generate_access_code()
        token["scopes"] = " ".join(token_data["scopes"])
        try:
            self.storage.insert_one(token)
        except storage_errors.ConflictError:
            raise api_errors.ConflictError(
                message="Token already exists for this user and client",
                client_id=token_data["client_id"],
                user_id=token_data["user_id"]
            ) from None
        return token
