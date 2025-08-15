"""campus.models.token

(Authorization) Token model for the Campus API.

Tokens are tagged to a specific client (by client_id), user (by user_id),
and session (by session_id).
"""

from campus.common import devops
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
            ...
        )
    """
    storage.init_table(schema)


class Tokens:
    """Token model for handling database operations related to tokens."""

    def __init__(self):
        """Initialize the Token model with a table storage interface."""
        self.storage = get_table(TABLE)

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
