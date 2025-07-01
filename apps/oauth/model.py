"""apps.oauth.model

This module defines models used in third party OAuth authentication.

The models are used to store auth session data and user credentials.
"""

from typing import TypedDict

from common.drum.mongodb import get_db, get_drum
from common.schema import UserID
from common.utils import utc_time


TABLE = "integrations"


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
    provider_data: dict[str, "IntegrationProviderRecord"]


class IntegrationProviderRecord(TypedDict, total=False):
    """Provider-specific integration records for each user."""
    oauth_session: "OAuthSessionRecord"  # OAuth session data for the integration
    credentials: "ProviderCredentialsRecord"  # Credentials for the integration


class OAuthSessionRecord(TypedDict, total=False):
    """OAuthRecord type for OAuth authentication session data."""
    created_at: str  # ISO 8601 timestamp of when the record was created
    scopes: list[str]  # List of scopes requested/granted during the OAuth flow
    state: str  # Randomly generated state string to prevent CSRF attacks
    code: str  # The authorization code received from the OAuth provider


class ProviderCredentialsRecord(TypedDict, total=False):
    """CredentialsRecord type for storing provider credentials for the user.
    
    This is expected to be access and refresh tokens.
    """
    access_token: str  # The access token issued by the OAuth provider
    refresh_token: str  # The refresh token issued by the OAuth provider


class OAuthSession:
    """OAuthSession model for managing OAuth sessions.

    Each session stores:
    - created_at: Timestamp of when the session was created
    - user_id: The ID of the user associated with the session
    - scopes: List of scopes requested/granted
    - state: A randomly generated state string to prevent CSRF attacks
    - code: The authorization code received from the OAuth provider
    """

    def __init__(self, user_id: UserID):
        """Initialize the Circle model with a storage interface."""
        self.user_id = user_id
        self.storage = get_drum()

    def init_record(self) -> None:
        """Initialize a new session record for the given user.

        Verify that the record does not exist before creating it.
        """
        db = get_db()
        record = IntegrationRecord(user_id=self.user_id, provider_data={})
        db[TABLE].insert_one(record)

    def get(self, provider: str) -> OAuthSessionRecord | None:
        """Retrieve the OAuth session record for a user and provider."""
        db = get_db()
        record = db[TABLE].find_one(
            {"user_id": self.user_id},
            {f"{provider}.oauth_session": 1}
        )
        if not record:
            return None
        return record.get(provider, {}).get("oauth_session")

    def new(
            self,
            provider: str,
            scopes: list[str],
            code: str,
            state: str = "",
    ) -> None:
        """Create a new OAuth session record."""
        db = get_db()
        record = db[TABLE].find_one({"user_id": self.user_id})
        if not record:
            self.init_record()
        db[TABLE].update_one(
            {"user_id": self.user_id},
            {"$set": {
                f"{provider}.oauth_session": {
                    "created_at": utc_time.now(),
                    "scopes": scopes,
                    "state": state,
                    "code": code
                }
            }}
        )


class ProviderCredentials:
    """ProviderCredentials model for managing OAuth provider credentials.

    The credentials are used to store user access and refresh tokens.
    """

    def __init__(self, user_id: UserID):
        """Initialize the ProviderCredentials model with a storage interface."""
        self.user_id = user_id
        self.storage = get_drum()

    def get_access_token(
            self,
            provider: str
    ) -> str | None:
        """Retrieve the access token for a user and provider."""
        db = get_db()
        record = db[TABLE].find_one(
            {"user_id": self.user_id},
            {f"{provider}.credentials.access_token": 1}
        )
        if not record:
            return None
        return record.get(provider, {}).get("credentials", {}).get("access_token")

    def set_access_token(
            self,
            provider: str,
            access_token: str,
    ) -> None:
        """Set the access token for a user and provider."""
        db = get_db()
        db[TABLE].update_one(
            {"user_id": self.user_id},
            {"$set": {
                f"{provider}.credentials": {
                    "access_token": access_token,
                }
            }}
        )

    def get_refresh_token(
            self,
            provider: str
    ) -> str | None:
        """Retrieve the refresh token for a user and provider."""
        db = get_db()
        record = db[TABLE].find_one(
            {"user_id": self.user_id},
            {f"{provider}.credentials.refresh_token": 1}
        )
        if not record:
            return None
        return record.get(provider, {}).get("credentials", {}).get("refresh_token")

    def set_refresh_token(
            self,
            provider: str,
            refresh_token: str,
    ) -> None:
        """Set the refresh token for a user and provider."""
        db = get_db()
        db[TABLE].update_one(
            {"user_id": self.user_id},
            {"$set": {
                f"{provider}.credentials.refresh_token": refresh_token
            }}
        )
