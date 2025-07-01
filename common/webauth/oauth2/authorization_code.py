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

TIMEOUT = 10  # Default timeout for requests in seconds


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
    state: NotRequired[str]  # State parameter for CSRF protection


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
    """Configures OAuth2 Authorization Code flow for a specified provider
    (google, github, discord, ...).

    The attributes are typically provided from a config file.
    """
    authorization_url: Url
    token_url: Url
    headers: dict[str, str]
    user_info_url: Url | None
    extra_params: dict[str, str]
    token_params: dict[str, str]
    user_info_params: dict[str, str]

    def __init__(self, **config: Unpack[OAuth2AuthorizationCodeConfigSchema]):
        """Initialize with OAuth2 Authorization Code flow configuration."""
        super().__init__(**config)
        self.authorization_url = config["authorization_url"]
        self.token_url = config["token_url"]
        self.headers = config.get("headers", {})
        self.user_info_url = config.get("user_info_url", None)
        self.extra_params = config.get("extra_params", {})
        self.token_params = config.get("token_params", {})
        self.user_info_params = config.get("user_info_params", {})

    def get_user_info(self, access_token: str) -> dict:
        """Fetch user info from the provider's user info endpoint."""
        if not self.user_info_url:
            return {}
        headers = {
            **self.headers,
            "Authorization": f"Bearer {access_token}",
            **self.user_info_params
        }
        resp = requests.get(
            self.user_info_url,
            headers=headers,
            timeout=TIMEOUT
        )
        try:
            return resp.json()
        except Exception as err:
            raise OAuth2SecurityError("Failed to fetch user info") from err


class OAuth2AuthorizationCodeSession:
    """Implements the OAuth2 Authorization Code flow session for a specified
    provider (google, github, discord, ...).

    While OAuth2AuthorizationCodeFlowScheme holds the provider config,
    OAuth2AuthorizationCodeSession handles the actual flow session for a single
    user sign-in.

    Each session:
    - is for a single user only
    - is assumed to be the only active session for that user
    - is short-lived (typically a few minutes)
    - is identified by a unique state hash

    This class may be subclassed by specific OAuth2 providers to implement
    provider-specific logic, such as custom headers or additional parameters.
    """

    def __init__(
            self,
            client_id: str,
            redirect_uri: Url,
            scopes: list[str],
            *,
            provider: OAuth2AuthorizationCodeFlowScheme,
    ):
        """Return the base parameters for the authorization request.

        Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.1
        """
        self.provider = provider
        self.client_id = client_id
        self.response_type = "code"
        self.redirect_uri = redirect_uri
        self.scopes = scopes
        # TODO: Set unique state for CSRF protection
        # https://developers.google.com/identity/openid-connect/openid-connect#python
        self.state = ""

    def get_authorization_url(self, **additional_params: dict[str, str]) -> str:
        """Return the authorization URL for redirect, with provider-specific
        params.

        Subclasses should extend this method to implement provider-specific
        logic, such as custom headers or additional parameters.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": self.response_type,
            "scope": " ".join(self.scopes),
            "state": self.state,
            **self.provider.extra_params,
            **additional_params
        }
        return f"""{self.provider.authorization_url}?{urlencode(params)}"""

    def exchange_code_for_token(
            self,
            code: str,
            client_secret: str,
    ) -> AuthorizationResponseSchema | AuthorizationErrorResponseSchema:
        """Exchange authorization code for access token."""
        params = {
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code": code,
            "client_secret": client_secret,
        }
        resp = requests.post(
            self.provider.token_url,
            params=params,
            headers=self.provider.headers,
            timeout=TIMEOUT
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
            if "error" in body:
                return AuthorizationErrorResponseSchema(**body)
            raise OAuth2SecurityError(
                "Invalid response from token endpoint, missing 'code' or 'error'."
            )


__all__ = [
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2AuthorizationCodeFlowScheme",
]
