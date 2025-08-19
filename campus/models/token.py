"""campus.models.token

(Bearer) Token model for the Campus API.

Tokens are issued for:
- a specific Campus client (by client_id)
- a specific Campus user (by user_id)
- specific scopes

Tokens follow storage interface requirements and will have `id` and `created_at` fields.

The browser/device is expected to store the token id in a client-side cookie. This enables multiple sign-in sessions per user-device.

Tokens are long-lived and the session stored by the browser may persist over multiple days.
"""

from typing import TypedDict

from campus.common import devops
from campus.common.errors import api_errors
from campus.common.utils import secret, uid, utc_time
from campus.common.schema import CampusID, UserID
from campus.models.base import BaseRecord
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
    schema = f"""
        CREATE TABLE IF NOT EXISTS "{TABLE}" (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            expires_at TEXT,
            client_id TEXT,
            user_id TEXT,
            agent_string TEXT,
            access_token TEXT,
            scopes TEXT,
            UNIQUE(agent_id),
            UNIQUE
        )
    """
    storage.init_table(schema)


class TokenRecord(BaseRecord):
    """Schema for a full token record."""
    expires_at: str
    client_id: CampusID
    user_id: UserID
    agent_string: str
    access_token: str
    scopes: str


class TokenNew(TypedDict):
    """Schema for a new token request."""
    client_id: CampusID
    user_id: UserID
    agent_string: str
    scopes: list[str]


class Tokens:
    """Token model for handling database operations related to tokens."""

    def __init__(self):
        """Initialize the Token model with a table storage interface."""
        self.storage = get_table(TABLE)

    def delete(self, token_id: CampusID) -> None:
        """Delete a token from the database."""
        self.storage.delete_by_id(token_id)

    def find(self, **match: str) -> list[dict]:
        """Retrieve a list of matching tokens. 

        This is intended for session retrieval by user and/or client, 
        and not meant for authentication. 
        For security reasons, the token id, access_token and expiry
        are stripped.
        """
        assert "id" not in match, (
            "find() by id is not allowed.\n" 
            "use get() instead."
        )
        tokens = self.storage.get_matching(match)
        for token in tokens:
            del token["id"]
            del token["access_token"]
            del token["expires_at"]
        return tokens

    def get(self, token_id: CampusID) -> dict:
        """Retrieve a token from the database by its ID."""
        return self.storage.get_by_id(token_id)

    def new(self, token_data: TokenNew, *, expiry_seconds: int) -> dict:
        """Create a new token in the database."""
        token = dict(token_data)
        token["id"] = uid.generate_category_uid("token")
        now = utc_time.now()
        token["created_at"] = utc_time.to_rfc3339(now)
        token["expires_at"] = utc_time.to_rfc3339(
            utc_time.after(now, seconds=expiry_seconds)
        )
        token["access_token"] = secret.generate_access_code()
        token["scopes"] = " ".join(token_data.get("scopes", []))
        self.storage.insert_one(token)
        return token

    def of(self, access_token: str) -> dict:
        """Retrieve a token by its access token."""
        toks = self.storage.get_matching({"access_token": access_token})
        if not toks:
            raise api_errors.NotFoundError(
                message="Token not found",
                access_token=access_token
            )
        token = toks[0]
        return token

    def validate_scope(
            self,
            session: dict,
            scopes: str | list[str]
    ) -> list[str]:
        """Validate the requested scopes against the session's granted scopes.
        """
        if isinstance(scopes, str):
            scopes = scopes.split(" ")
        return [
            scope for scope in scopes
            if scope not in session["scopes"]
        ]
