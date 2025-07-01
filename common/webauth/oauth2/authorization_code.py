"""common.webauth.oauth2.authorization_code

OAuth2 Authorization Code flow configs and models.
"""

from typing import Any, Literal, NotRequired, Required, TypedDict, Unpack
from urllib.parse import urlencode

import requests

from common.drum.mongodb import get_db
from common.utils import uid, utc_time

from .base import (
    OAuth2AuthorizationCodeConfigSchema,
    OAuth2FlowScheme,
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

OAUTH_EXPIRY_MINUTES = 10  # Default expiry time for OAuth2 sessions in minutes
TIMEOUT = 10  # Default timeout for requests in seconds
TABLE = "webauth"


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
    redirect_uri: Url
    headers: dict[str, str]
    user_info_url: Url | None
    extra_params: dict[str, str]
    token_params: dict[str, str]
    user_info_params: dict[str, str]
    scopes: list[str]

    def __init__(self, provider: str, **config: Unpack[OAuth2AuthorizationCodeConfigSchema]):
        """Initialize with OAuth2 Authorization Code flow configuration."""
        super().__init__(provider, **config)
        self.authorization_url = config["authorization_url"]
        self.token_url = config["token_url"]
        self.redirect_uri = config.get("redirect_uri", "")
        self.scopes = config["scopes"]
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

    def create_session(
            self,
            client_id: str,
            scopes: list[str],
            target: Url,
    ) -> "OAuth2AuthorizationCodeSession":
        """Create a new OAuth2 Authorization Code flow session."""
        return OAuth2AuthorizationCodeSession(
            scopes=scopes,
            target=target,
            provider=self,
            client_id=client_id,
        )

    def retrieve_session(
            self,
            state: str
    ) -> "OAuth2AuthorizationCodeSession | None":
        """Retrieve an existing OAuth2 Authorization Code flow session by state."""
        db = get_db()
        record = db[TABLE].find_one({"state": state})
        if not record:
            return None
        return OAuth2AuthorizationCodeSession(
            client_id=record["client_id"],
            scopes=record["scopes"],
            target=record["target"],
            state=record["state"],
            provider=self
        )


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

    The attributes that the class possesses are used for OAuth2 flow or
    common provider parameters.

    This class may be subclassed by specific OAuth2 providers to implement
    provider-specific logic, such as custom headers or additional parameters.
    """
    provider: OAuth2AuthorizationCodeFlowScheme
    client_id: str
    created_at: str  # RFC3339 timestamp of when the session was created
    response_type: Literal["code"]
    scopes: list[str]
    state: str  # Unique state for CSRF protection
    target: Url  # URL to redirect to after successful authentication

    def __init__(
            self,
            scopes: list[str],
            target: Url,
            state: str = "",
            *,
            provider: OAuth2AuthorizationCodeFlowScheme,
            client_id: str,
    ):
        """Return the base parameters for the authorization request.

        Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1.1
        """
        self.provider = provider
        self.created_at = utc_time.to_rfc3339(utc_time.now())
        self.client_id = client_id
        self.response_type = "code"
        self.scopes = scopes
        self.state = state or uid.generate_category_uid("oauthsession")
        self.target = target

    def delete(self) -> None:
        """Delete the session from the database or cache.

        This method should be implemented by subclasses to remove the session
        data, such as from a database or cache.
        """
        db = get_db()
        db[TABLE].delete_one({"state": self.state})

    def exchange_code_for_token(
            self,
            code: str,
            client_secret: str,
    ) -> AuthorizationResponseSchema | AuthorizationErrorResponseSchema:
        """Exchange authorization code for access token."""
        params = {
            "grant_type": "authorization_code",
            "redirect_uri": self.provider.redirect_uri,
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

    def get_authorization_url(self, **additional_params: dict[str, str]) -> str:
        """Return the authorization URL for redirect, with provider-specific
        params.

        Subclasses should extend this method to implement provider-specific
        logic, such as custom headers or additional parameters.
        """
        params = {
            "client_id": self.client_id,
            # TODO: Add base URL to redirect_uri
            "redirect_uri": self.provider.redirect_uri,
            "response_type": self.response_type,
            "scope": " ".join(self.scopes),
            "state": self.state,
            **self.provider.extra_params,
            **additional_params
        }
        return f"""{self.provider.authorization_url}?{urlencode(params)}"""

    def is_expired(self) -> bool:
        """Check if the session has expired.

        This method checks if the session was created more than 10 minutes ago.
        If so, it considers the session expired.
        """
        created_at = utc_time.from_rfc3339(self.created_at)
        expires_at = utc_time.after(created_at, minutes=OAUTH_EXPIRY_MINUTES)
        return expires_at > utc_time.now()

    def store(self) -> None:
        """Store the session in the database or cache.

        This method should be implemented by subclasses to persist the session
        data, such as in a database or cache.
        """
        db = get_db()
        db[TABLE].insert_one(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the session."""
        return {
            "provider": self.provider.provider,
            "client_id": self.client_id,
            "created_at": self.created_at,
            "response_type": self.response_type,
            "scopes": self.scopes,
            "state": self.state,
        }


__all__ = [
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2AuthorizationCodeFlowScheme",
]
