"""apps/common/webauth/oauth2/authorization_code

OAuth2 Authorization Code flow configs and models.
"""

from typing import Required, Unpack
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
            state: str,
            client_id: str,
            redirect_uri: Url,
            user_id: str,  # user's email for login_hint
    ) -> str:
        """Return the authorization URL for redirect, with provider-specific
        params.
        """
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "login_hint": user_id
        }
        params.update(getattr(self, "extra_params", {}) or {})
        base_url = getattr(self, "authorization_url", "")
        return f"{base_url}?{urlencode(params)}"

    def exchange_code_for_token(
            self,
            code: str,
            client_id: str,
            client_secret: str,
            redirect_uri: str
    ) -> dict:
        """Exchange authorization code for access token."""
        data = dict(
            grant_type="authorization_code",
            code=code,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret,
            **self.token_params,
        )
        resp = requests.post(
            self.token_url,
            data=data,
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
        headers = {"Authorization": f"Bearer {access_token}"}
        headers.update(self.user_info_params)
        resp = requests.get(self.user_info_url, headers=headers, timeout=10)
        try:
            return resp.json()
        except Exception as err:
            raise OAuth2SecurityError("Failed to fetch user info") from err


__all__ = [
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2AuthorizationCodeFlowScheme",
]
