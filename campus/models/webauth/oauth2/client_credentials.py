"""campus.models.webauth.oauth2.client_credentials

OAuth2 Client Credentials flow schemas and models.

Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.4
"""

__all__ = ["OAuth2ClientCredentialsFlowScheme"]

from typing import Any

import requests

from campus.common import integration, schema
from campus.common.errors import token_errors
from campus.models import token

from .base import (
    OAuth2FlowScheme,
)

TIMEOUT = 10  # Default timeout for requests in seconds

tokens = token.Tokens()


# class ClientCredentialsTokenRequestSchema(TypedDict):
#     """Request schema for OAuth2 Client Credentials flow.
#     Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.4.2
#     """
#     grant_type: Literal["client_credentials"]  # Must be "client_credentials"
#     scope: NotRequired[str]  # Space-separated scopes for the request


# class ClientCredentialsTokenResponseSchema(TypedDict):
#     """Response schema for OAuth2 Client Credentials flow.
#     Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.4.3
#     """
#     access_token: str  # Access token issued by the OAuth2 provider
#     token_type: str  # Type of the token (e.g., "Bearer")
#     expires_in: NotRequired[int]  # Lifetime of the access token in seconds
#     scope: NotRequired[str]  # Scopes granted by the access token


# class OAuth2ClientCredentialsConfigSchema(TypedDict):
#     """Schema for OAuth2 Client Credentials configuration."""
#     security_scheme: Literal["oauth2"]
#     flow: Literal["clientCredentials"]
#     scopes: list[str]
#     token_url: str
#     headers: NotRequired[dict[str, str]]


class OAuth2ClientCredentialsFlowScheme(OAuth2FlowScheme):
    """Configures OAuth2 Client Credentials flow for a specified provider
    (discord, github, etc.).

    The attributes are typically provided from a config file.
    """
    flow: integration.config.OAuth2Flow = "clientCredentials"
    token_url: str
    headers: dict[str, str]
    scopes: list[str]

    def __init__(
            self,
            provider: str,
            token_url: schema.Url,
            scopes: list[str],
            headers: dict[str, str] | None = None,
    ):
        super().__init__(provider)
        self.token_url = token_url
        self.scopes = scopes
        self.headers = headers or {}

    @classmethod
    def from_config(
            cls: type["OAuth2ClientCredentialsFlowScheme"],
            provider: str,
            config: dict[str, Any],
    ) -> "OAuth2ClientCredentialsFlowScheme":
        """Create an OAuth2ClientCredentialsFlowScheme instance from
        config.
        """
        return cls(
            provider=provider,
            token_url=config["token_url"],
            scopes=config["scopes"],
            headers=config.get("headers", {})
        )

    def get_token(
            self,
            *,
            auth: tuple[str, str] | None = None,
            client_id: str | None = None,
            client_secret: str | None = None
    ) -> token.TokenRecord:
        """Retrieve access token using client credentials.

        Args:
            auth: Optional tuple of (username, password) for basic auth.
                Used by Discord
            client_id, client_secret: Client ID and secret.
                Used by Google, GitHub, etc.
        """
        # TODO: refactor into client_credentials submodule
        # Only pass auth or client_id/client_secret, not both
        if auth and (client_id or client_secret):
            raise ValueError(
                "Provide only auth or client_id/client_secret, not both"
            )
        if auth:
            resp = requests.post(
                url=self.token_url,
                data={
                    "grant_type": "client_credentials",
                },
                headers=self.headers,
                auth=auth,
                timeout=TIMEOUT
            )
        else:  # client credentials
            if not client_id or not client_secret:
                raise ValueError(
                    "client_id and client_secret must be provided"
                )
            resp = requests.post(
                url=self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers=self.headers,
                timeout=TIMEOUT
            )
        token_payload = resp.json()
        if "error" in token_payload:
            token_errors.raise_from_json(token_payload)
        return token.TokenRecord.from_dict(token_payload)
