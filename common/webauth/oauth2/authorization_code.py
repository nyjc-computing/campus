"""common.webauth.oauth2.authorization_code

OAuth2 Authorization Code flow configs and models.
"""

from typing import Literal, NotRequired, Required, TypedDict, Unpack
from urllib.parse import urlencode

import requests

from .base import (
    OAuth2ConfigSchema,
    OAuth2FlowScheme,
    OAuth2InvalidRequestError,
    OAuth2SecurityError,
)

Url = str
AuthorizationErrorCode = Literal[
    "invalid_request",
    "unauthorized_client",
    "access_denied",
    "unsupported_response_type",
    "invalid_scope",
    "server_error",
    "temporarily_unavailable",
]


class OAuth2AuthorizationCodeConfigSchema(OAuth2ConfigSchema, total=False):
    """OAuth2 Authorization Code flow configuration."""
    authorization_url: Required[Url]  # Required for authorization code flow
    token_url: Required[Url]  # Required for token exchange
    headers: dict[str, str]  # Optional, for custom headers in requests
    user_info_url: Url  # Optional, for user info endpoint
    extra_params: dict[str, str]  # Optional, for additional parameters in requests
    token_params: dict[str, str]  # Optional, for custom token exchange
    user_info_params: dict[str, str]  # Optional, for custom user info requests


class AuthorizationRequestSchema(TypedDict, total=False):
    """Request schema for OAuth2 Authorization Code flow.
    Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.1

    NotRequired fields will be filled in by auth flow
    """
    response_type: NotRequired[str]  # Must be 'code'
    client_id: Required[str]  # Client ID of the OAuth2 application
    redirect_uri: Url  # Redirect URI registered with the OAuth2 provider
    scope: str  # Space-separated scopes for the request
    state: str  # State parameter for CSRF protection


class AuthorizationResponseSchema(TypedDict, total=False):
    """Response schema for OAuth2 Authorization Code flow.
    Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.2

    Response may be a success or error response.
    Success response will contain the authorization code and state.
    Error response will contain an error code and description.
    """
    code: str  # Authorization code received from the provider
    state: str  # State parameter for CSRF protection


class AuthorizationErrorResponseSchema(TypedDict, total=False):
    """Error response schema for OAuth2 Authorization Code flow.
    Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.2

    NotRequired fields will be filled in by redirect endpoint.
    """
    error: AuthorizationErrorCode
    error_description: str  # Human-readable description of the error
    error_uri: Url
    state: str  # State parameter for CSRF protection, if provided


class TokenRequestSchema(TypedDict, total=False):
    """Request schema for exchanging authorization code for access token."""
    grant_type: NotRequired[str]  # Must be "authorization_code"
    code: Required[str]  # Authorization code received from the provider
    redirect_uri: Url  # Same redirect URI used in authorization request
    client_id: Required[str]  # Client ID of the OAuth2 application
    client_secret: str  # Client secret of the OAuth2 application


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
        self.scopes = kwargs.get("scopes", [])

    def get_authorization_url(
            self,
            **params: Unpack[AuthorizationRequestSchema]
    ) -> str:
        """Return the authorization URL for redirect, with provider-specific
        params.
        """
        if "response_type" in params and params["response_type"] != "code":
            raise OAuth2InvalidRequestError(
                "Invalid response_type, must be 'code' for authorization code flow."
            )
        params["response_type"] = "code"
        params["scope"] = " ".join(self.scopes)
        return f"""{self.authorization_url}?{urlencode(
            {**params, **self.extra_params})
        }"""

    def exchange_code_for_token(
            self,
            **params: Unpack[TokenRequestSchema],
    ) -> AuthorizationResponseSchema | AuthorizationErrorResponseSchema:
        """Exchange authorization code for access token."""
        if "grant_type" in params and params["grant_type"] != "authorization_code":
            raise OAuth2InvalidRequestError(
                "Invalid grant_type, must be 'authorization_code' for authorization code flow."
            )
        params["grant_type"] = "authorization_code"
        resp = requests.post(
            self.token_url,
            params=params,
            headers=self.headers,
            timeout=10
        )
        try:
            body = resp.json()
        except Exception as err:
            raise OAuth2SecurityError(
                "Failed to exchange code for token"
            ) from err
        else:
            if "code" in body:
                return AuthorizationResponseSchema(**body)
            elif "error" in body:
                return AuthorizationErrorResponseSchema(**body)
            else:
                raise OAuth2SecurityError(
                    "Invalid response from token endpoint, missing 'code' or 'error'."
                )

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
