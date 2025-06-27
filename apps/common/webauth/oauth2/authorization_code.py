"""apps/common/webauth/oauth2/authorization_code

OAuth2 Authorization Code flow configs and models.
"""

from typing import NotRequired, Required, TypedDict, Unpack
from urllib.parse import urlencode

import requests

from .base import (
    OAuth2ConfigSchema,
    OAuth2FlowScheme,
    OAuth2SecurityError
)

Url = str


class OAuth2AuthorizationCodeConfigSchema(OAuth2ConfigSchema, total=False):
    """OAuth2 Authorization Code flow configuration."""
    authorization_url: Required[Url]  # Required for authorization code flow
    token_url: Required[Url]  # Required for token exchange
    headers: dict[str, str]  # Optional, for custom headers in requests
    user_info_url: Url  # Optional, for user info endpoint
    extra_params: dict[str, str]  # Optional, for additional parameters in requests
    token_params: dict[str, str]  # Optional, for custom token exchange
    user_info_params: dict[str, str]  # Optional, for custom


class AuthorizationUrlRequestSchema(TypedDict, total=False):
    """Request schema for getting the authorization URL."""
    state: str  # State parameter for CSRF protection
    client_id: str  # Client ID of the OAuth2 application
    redirect_uri: Url  # Redirect URI registered with the OAuth2 provider
    login_hint: str  # User's email or identifier for login_hint
    response_type: NotRequired[str]
    scope: NotRequired[str]  # Space-separated scopes for the request


class TokenRequestSchema(TypedDict, total=False):
    """Request schema for exchanging authorization code for access token."""
    code: str  # Authorization code received from the provider
    redirect_uri: Url  # Same redirect URI used in authorization request
    client_id: str  # Client ID of the OAuth2 application
    client_secret: str  # Client secret of the OAuth2 application
    grant_type: NotRequired[str]  # Will be "authorization_code"


class OAuth2AuthorizationCodeFlowScheme(OAuth2FlowScheme):
    """Implements OAuth2 Authorization Code flow.

    Uses a user-agent redirect to obtain an authorization code, then exchanges
    it for an access token.
    """

    def __init__(self, **kwargs: Unpack[OAuth2AuthorizationCodeConfigSchema]):
        """Initialize with OAuth2 Authorization Code flow configuration."""
        super().__init__(**kwargs)
        self.authorization_url = kwargs["authorization_url"]
        self.token_url = kwargs["token_url"]
        self.headers = kwargs.get("headers", {})
        self.user_info_url = kwargs.get("user_info_url", None)
        self.extra_params = kwargs.get("extra_params", {})
        self.token_params = kwargs.get("token_params", {})
        self.user_info_params = kwargs.get("user_info_params", {})

    def get_authorization_url(
            self,
            **params: Unpack[AuthorizationUrlRequestSchema]
    ) -> str:
        """Return the authorization URL for redirect, with provider-specific
        params.
        """
        params["response_type"] = "code"
        params["scope"] = " ".join(self.scopes)
        return f"""{self.authorization_url}?{urlencode(
            {**params, **self.extra_params})
        }"""

    def exchange_code_for_token(
            self,
            **data: Unpack[TokenRequestSchema],
    ) -> dict:
        """Exchange authorization code for access token."""
        data["grant_type"] = "authorization_code"
        resp = requests.post(
            self.token_url,
            data={**data, **self.token_params},
            headers=self.headers,
            timeout=10
        )
        try:
            return resp.json()
        except Exception as err:
            raise OAuth2SecurityError(
                "Failed to exchange code for token"
            ) from err

    def get_user_info(self, access_token: str) -> dict:
        """Fetch user info from the provider's user info endpoint."""
        if not self.user_info_url:
            return {}
        headers = {
            **self.headers,
            "Authorization": f"Bearer {access_token}",
            **self.user_info_params
        }
        resp = requests.get(self.user_info_url, headers=headers, timeout=10)
        try:
            return resp.json()
        except Exception as err:
            raise OAuth2SecurityError("Failed to fetch user info") from err


__all__ = [
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2AuthorizationCodeFlowScheme",
]
