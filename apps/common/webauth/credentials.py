"""apps.common.webauth.credentials

This module defines third party credentials storage models.

Credentials records are identified by user_id, with each provider's credentials
stored under a provider key.
"""

from typing import TypedDict

from common.drum.mongodb import get_db, get_drum
from common.schema import UserID


TABLE = "credentials"


def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    db = get_db()


class IntegrationRecord(TypedDict, total=False):
    """IntegrationRecord type for third-party OAuth integration data."""
    user_id: UserID  # The ID of the user associated with the integration
    # Provider-specific data, e.g., access tokens, refresh tokens
    provider_data: dict[str, "ProviderCredentialsRecord"]


class ProviderCredentialsRecord(TypedDict, total=False):
    """CredentialsRecord type for storing provider credentials for the user.
    
    This is expected to be access and refresh tokens.
    """
    scopes: list[str]  # Scopes granted by the OAuth provider
    access_token: str  # The access token issued by the OAuth provider
    refresh_token: str  # The refresh token issued by the OAuth provider


class ProviderCredentials:
    """ProviderCredentials model for managing OAuth provider credentials.

    The credentials are used to store user access and refresh tokens.
    """

    def __init__(self, user_id: UserID, provider: str):
        """Initialize the ProviderCredentials model with a storage interface."""
        self.user_id = user_id
        self.provider = provider
        self.storage = get_drum()

    def get(self) -> str | None:
        """Retrieve the access token for a user and provider."""
        db = get_db()
        record = db[TABLE].find_one(
            {"user_id": self.user_id},
            {f"{self.provider}": 1}
        )
        if not record:
            return None
        return record.get(self.provider)

    def set_access_token(self, access_token: str) -> None:
        """Set the access token for a user and provider."""
        db = get_db()
        db[TABLE].update_one(
            {"user_id": self.user_id},
            {"$set": {
                f"{self.provider}.access_token": access_token
            }}
        )

    def set_refresh_token(self, refresh_token: str) -> None:
        """Set the refresh token for a user and provider."""
        db = get_db()
        db[TABLE].update_one(
            {"user_id": self.user_id},
            {"$set": {
                f"{self.provider}.refresh_token": refresh_token
            }}
        )

    def set_scopes(self, scopes: list[str]) -> None:
        """Set the scopes for a user and provider."""
        db = get_db()
        db[TABLE].update_one(
            {"user_id": self.user_id},
            {"$set": {
                f"{self.provider}.scopes": scopes
            }}
        )
