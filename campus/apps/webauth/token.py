"""apps.common.webauth.token

Token management schemas and models
"""

from typing import NotRequired, TypedDict, Unpack

from campus.common.utils import utc_time

EXPIRY_THRESHOLD = 300  # 5 minutes in seconds, used to check token expiry


class TokenResponseSchema(TypedDict):
    """Response schema for access token exchange."""
    access_token: str  # Access token issued by the OAuth2 provider
    token_type: str  # Type of the token (e.g., "Bearer")
    expires_in: int  # Lifetime of the access token in seconds
    scope: str  # Scopes granted by the access token
    refresh_token: NotRequired[str]  # Optional refresh token for long-lived sessions
    refresh_token_expires_in: NotRequired[int]  # Lifetime of the refresh token in seconds


class TokenSchema(TypedDict):
    """Schema for token storage."""
    token_type: str
    access_token: str
    expires_at: utc_time.datetime
    scopes: list[str]
    refresh_token: NotRequired[str]
    refresh_token_expires_at: NotRequired[utc_time.datetime]


class CredentialToken:
    """Model for credential tokens issued by providers."""
    provider: str  # e.g. "google", "github", etc.
    token: TokenSchema  # The token data

    def __init__(self, provider: str, **token: Unpack[TokenSchema]):
        self.provider = provider
        self.token = token

    def __repr__(self) -> str:
        """String representation of the CredentialToken."""
        return f"CredentialToken(provider={self.provider}, token={self.token})"
    
    @property
    def token_type(self) -> str:
        return self.token["token_type"]

    @property
    def access_token(self) -> str:
        return self.token["access_token"]
    
    @property
    def expires_at(self) -> utc_time.datetime:
        return self.token["expires_at"]
    
    @property
    def scopes(self) -> list[str]:
        return self.token["scopes"]
    
    @property
    def refresh_token(self) -> str | None:
        return self.token.get("refresh_token")
    
    @property
    def refresh_token_expires_at(self) -> utc_time.datetime | None:
        return self.token.get("refresh_token_expires_at")
        
    def to_dict(self) -> TokenSchema:
        """Convert the token to a dictionary representation."""
        return self.token
    
    def is_expired(self, from_time: utc_time.datetime | None = None) -> bool:
        """Check if the token is expired based on the current time."""
        return utc_time.is_expired(
            self.token["expires_at"],
            from_time=from_time or utc_time.now(),
            threshold=EXPIRY_THRESHOLD
        )
    
    def refresh_from_response(self, response: TokenResponseSchema) -> None:
        """Update the token from a token response."""
        token = self.prepare_token_from_response(response)
        self.token = token

    @classmethod
    def from_dict(cls, provider: str, token: TokenSchema) -> "CredentialToken":
        """Create a CredentialToken instance from a dictionary."""
        return cls(provider, **token)

    @classmethod
    def from_response(cls, provider: str, response: TokenResponseSchema) -> "CredentialToken":
        """Create a CredentialToken instance from a token response."""
        token = cls.prepare_token_from_response(response)
        return cls(provider, **token)

    @staticmethod
    def prepare_token_from_response(response: TokenResponseSchema) -> TokenSchema:
        """Prepare a token dictionary from a token response."""
        token: TokenSchema = {
            "token_type": response["token_type"],
            "access_token": response["access_token"],
            "expires_at": utc_time.after(seconds=response["expires_in"]),
            "scopes": response["scope"].split(" "),
        }
        if "refresh_token" in response:
            token["refresh_token"] = response["refresh_token"]
        if "refresh_token_expires_in" in response:
            token["refresh_token_expires_at"] = utc_time.after(
                seconds=response["refresh_token_expires_in"]
            )
        return token