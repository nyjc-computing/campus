"""campus.common.webauth.oauth2.client_credentials

OAuth2 Client Credentials flow schemas and models.

Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.4
"""

__all__ = [
    "OAuth2ClientCredentialsConfigSchema",
    "OAuth2ClientCredentialsFlowScheme",
    "ClientCredentialsTokenRequestSchema",
    "ClientCredentialsTokenResponseSchema",
]

from typing import Any, Literal, NotRequired, TypedDict, Unpack

import requests

from campus.common.integration.schema import IntegrationConfigSchema
from campus.common.webauth.token import CredentialToken
from campus.common.utils import utc_time

from .base import (
    OAuth2AuthorizationCodeConfigSchema,
    OAuth2FlowScheme,
    OAuth2SecurityError,
)

TIMEOUT = 10  # Default timeout for requests in seconds


class ClientCredentialsTokenRequestSchema(TypedDict):
    """Request schema for OAuth2 Client Credentials flow.
    Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.4.2
    """
    grant_type: Literal["client_credentials"]  # Must be "client_credentials"
    scope: NotRequired[str]  # Space-separated scopes for the request


class ClientCredentialsTokenResponseSchema(TypedDict):
    """Response schema for OAuth2 Client Credentials flow.
    Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.4.3
    """
    access_token: str  # Access token issued by the OAuth2 provider
    token_type: str  # Type of the token (e.g., "Bearer")
    expires_in: NotRequired[int]  # Lifetime of the access token in seconds
    scope: NotRequired[str]  # Scopes granted by the access token


class OAuth2ClientCredentialsConfigSchema(TypedDict):
    """Schema for OAuth2 Client Credentials configuration."""
    security_scheme: Literal["oauth2"]
    flow: Literal["clientCredentials"]
    scopes: list[str]
    token_url: str
    headers: NotRequired[dict[str, str]]


class OAuth2ClientCredentialsFlowScheme(OAuth2FlowScheme):
    """Configures OAuth2 Client Credentials flow for a specified provider
    (discord, github, etc.).

    The attributes are typically provided from a config file.
    """
    token_url: str
    headers: dict[str, str]
    scopes: list[str]

    def __init__(self, provider: str, **config: Unpack[OAuth2ClientCredentialsConfigSchema]):
        """Initialize with OAuth2 Client Credentials flow configuration."""
        super().__init__(provider, **config)
        self.token_url = config["token_url"]
        self.scopes = config["scopes"]
        self.headers = config.get("headers", {})

    def get_app_token(
        self,
        client_id: str,
        client_secret: str,
        scopes: list[str] | None = None
    ) -> dict[str, Any]:
        """Get an application access token using Client Credentials flow.
        
        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            scopes: List of scopes to request (defaults to configured scopes)
            
        Returns:
            Token response from the OAuth2 provider
            
        Raises:
            OAuth2SecurityError: If token request fails
        """
        scopes = scopes or self.scopes
        
        # Prepare token request data
        data = {
            "grant_type": "client_credentials",
            "scope": " ".join(scopes) if scopes else "",
        }
        
        # Remove empty scope parameter
        if not data["scope"]:
            data.pop("scope")
        
        # Make token request with Basic Auth
        # Discord uses Basic Auth with client_id:client_secret
        resp = requests.post(
            url=self.token_url,
            data=data,
            headers=self.headers,
            auth=(client_id, client_secret),
            timeout=TIMEOUT
        )
        
        try:
            body = resp.json()
        except Exception as err:
            raise OAuth2SecurityError("Failed to get app token") from err
            
        # Check for error responses
        if "error" in body:
            error_msg = body.get("error_description", body["error"])
            raise OAuth2SecurityError(f"Token request failed: {error_msg}")
            
        return body

    def refresh_app_token(
        self,
        token: CredentialToken,
        client_id: str,
        client_secret: str,
        force: bool = False
    ) -> None:
        """Refresh an application access token.
        
        Args:
            token: The CredentialToken instance to refresh
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            force: If True, force refresh even if token is not expired
            
        Note:
            Client Credentials flow doesn't use refresh tokens.
            This method gets a new token instead.
        """
        if not token.is_expired() and not force:
            return
            
        # Get new token (Client Credentials doesn't have refresh tokens)
        new_token_response = self.get_app_token(
            client_id=client_id,
            client_secret=client_secret,
            scopes=token.scopes
        )
        
        # Update the token with new response
        token.refresh_from_response(new_token_response)

    @classmethod
    def from_json(
            cls,
            config: IntegrationConfigSchema,
            security: Literal["oauth2"] = "oauth2",
            **kwargs,
    ) -> "OAuth2ClientCredentialsFlowScheme":
        """Create OAuth2ClientCredentialsFlowScheme from JSON config.
        
        Args:
            config: Integration configuration dictionary
            security: Security scheme name (default: "oauth2")
            
        Returns:
            Configured OAuth2ClientCredentialsFlowScheme instance
        """
        security_config = config["security"][security]
        
        return cls(
            provider=config["provider"],
            **security_config
        )
