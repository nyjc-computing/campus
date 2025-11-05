"""campus.api.resources.token

Token resource for Campus API.
"""

import typing

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import utc_time
import campus.model
import campus.storage

token_storage = campus.storage.get_table("tokens")

DEFAULT_EXPIRY_SECONDS = utc_time.DAY_SECONDS * 30  # 30 days


def _from_record(
        record: dict[str, typing.Any],
) -> campus.model.Token:
    """Convert a storage record to a Token model instance."""
    # Parse scopes from space-separated string to list
    scopes = record.get('scopes', '')
    if isinstance(scopes, str):
        scopes_list = scopes.split(' ') if scopes else []
    else:
        scopes_list = scopes

    return campus.model.Token(
        id=schema.CampusID(record['id']),
        created_at=schema.DateTime(record['created_at']),
        expires_at=schema.DateTime(record['expires_at']),
        client_id=schema.CampusID(record['client_id']),
        user_id=schema.UserID(record['user_id']),
        scopes=scopes_list,
        expiry_seconds=None  # Already have expires_at
    )


def _to_record(token: campus.model.Token) -> dict[str, typing.Any]:
    """Convert a Token model instance to a storage record."""
    record = token.to_storage()
    # Convert scopes list to space-separated string for storage
    if isinstance(record.get('scopes'), list):
        record['scopes'] = ' '.join(record['scopes'])
    return record


class TokensResource:
    """Represents the tokens resource in Campus API Schema."""

    @staticmethod
    def init_storage() -> None:
        """Initialize storage for token management."""
        token_storage.init_from_model("tokens", campus.model.Token)

    def __getitem__(self, token_id: schema.CampusID) -> "TokenResource":
        """Get a token resource by token ID.

        Args:
            token_id: The token ID (access token)

        Returns:
            TokenResource instance
        """
        return TokenResource(token_id)

    def find(
            self,
            **match: typing.Any
    ) -> list[campus.model.Token]:
        """Retrieve a list of matching tokens.

        Args:
            **match: Matching criteria (e.g., client_id, user_id)

        Returns:
            List of Token instances
        """
        if schema.CAMPUS_KEY in match:
            raise ValueError(
                "'id=' keyword argument in find() is not allowed.\n"
                "Use get() or __getitem__() instead."
            )
        records = token_storage.get_matching(match)
        return [_from_record(record) for record in records]

    def get_by_client_user(
            self,
            client_id: schema.CampusID,
            user_id: schema.UserID
    ) -> campus.model.Token:
        """Get the token for a client/user pair.

        Args:
            client_id: The client identifier
            user_id: The user identifier

        Returns:
            Token instance

        Raises:
            NotFoundError: If token not found
            InternalError: If multiple tokens found
        """
        results = self.find(client_id=client_id, user_id=user_id)
        if len(results) == 0:
            raise api_errors.NotFoundError(
                "Token not found for this client and user",
                client_id=client_id,
                user_id=user_id
            )
        elif len(results) > 1:
            raise api_errors.InternalError(
                "Multiple tokens found for this client and user",
                client_id=client_id,
                user_id=user_id
            )
        return results[0]

    def new(
            self,
            *,
            client_id: schema.CampusID,
            user_id: schema.UserID,
            scopes: list[str],
            expiry_seconds: int = DEFAULT_EXPIRY_SECONDS
    ) -> campus.model.Token:
        """Create a new token.

        Args:
            client_id: The client identifier
            user_id: The user identifier
            scopes: List of scope strings
            expiry_seconds: Token expiry in seconds

        Returns:
            Token instance

        Raises:
            ConflictError: If token already exists for this user/client
        """
        token = campus.model.Token(
            client_id=client_id,
            user_id=user_id,
            scopes=scopes,
            expiry_seconds=expiry_seconds
        )
        try:
            token_storage.insert_one(_to_record(token))
        except campus.storage.errors.ConflictError:
            raise api_errors.ConflictError(
                "Token already exists for this user and client",
                client_id=client_id,
                user_id=user_id
            ) from None
        return token

    def sweep(
            self,
            *,
            at_time: schema.DateTime | None = None
    ) -> int:
        """Delete expired tokens from the database.

        Args:
            at_time: Reference time for expiry check (default: now)

        Returns:
            Number of deleted tokens
        """
        at_time = at_time or schema.DateTime.utcnow()
        all_tokens = self.find()
        expired_token_ids = [
            token.id for token in all_tokens
            if token.is_expired(at_time=at_time)
        ]
        for token_id in expired_token_ids:
            self[token_id].delete()
        return len(expired_token_ids)


class TokenResource:
    """Represents a single token in Campus API Schema."""

    def __init__(self, token_id: schema.CampusID):
        self.token_id = token_id

    def delete(self) -> None:
        """Delete the token record.

        Raises:
            NotFoundError: If token not found
        """
        try:
            token_storage.delete_by_id(self.token_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                f"Token '{self.token_id}' not found",
                token_id=self.token_id
            ) from None

    def get(self) -> campus.model.Token:
        """Get the token record.

        Returns:
            Token instance

        Raises:
            NotFoundError: If token not found
        """
        record = token_storage.get_by_id(self.token_id)
        if not record:
            raise api_errors.NotFoundError(
                f"Token '{self.token_id}' not found",
                token_id=self.token_id
            )
        return _from_record(record=record)

    def update(self, **updates: typing.Any) -> None:
        """Update the token record.

        Args:
            **updates: Fields to update

        Raises:
            NotFoundError: If token not found
        """
        campus.model.Token.validate_update(updates)
        # Convert scopes list to space-separated string if needed
        if 'scopes' in updates and isinstance(updates['scopes'], list):
            updates['scopes'] = ' '.join(updates['scopes'])
        try:
            token_storage.update_by_id(self.token_id, updates)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                f"Token '{self.token_id}' not found",
                token_id=self.token_id
            ) from None
