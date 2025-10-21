"""campus.common.webauth.oauth2.authorization_code

OAuth2 Authorization Code flow schemas and models.
"""

__all__ = [
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2AuthorizationCodeFlowScheme",
]

import logging
from typing import Any, Literal, NotRequired, Required, TypedDict, Unpack
from urllib.parse import urlencode

import requests
from flask import session as flask_session

from campus.common import schema
from campus.common.utils import uid, utc_time
from campus.common.webauth.http import HttpScheme
from campus.common.webauth.token import CredentialToken

from .base import (
    OAuth2AuthorizationCodeConfigSchema,
    OAuth2FlowScheme,
    OAuth2SecurityError,
)

Url = str

OAUTH_EXPIRY_MINUTES = 10  # Default expiry time for OAuth2 sessions in minutes
TIMEOUT = 10  # Default timeout for requests in seconds
TABLE = "webauth"

# Set up logger for OAuth2 flow
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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


class TokenRequestSchema(TypedDict, total=False):
    """Request schema for exchanging authorization code for access token."""
    grant_type: NotRequired[str]  # Must be "authorization_code"
    code: Required[str]  # Authorization code received from the provider
    redirect_uri: Url  # Same redirect URI used in authorization request
    client_id: Required[str]  # Client ID of the OAuth2 application
    client_secret: str  # Client secret of the OAuth2 application


class TokenResponseSchema(TypedDict):
    """Token schema as used by most providers."""
    token_type: HttpScheme
    scope: str
    access_token: str
    refresh_token: NotRequired[str]
    expires_in: NotRequired[int]  # Lifetime of the access token in seconds


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

    def retrieve_session(self) -> "OAuth2AuthorizationCodeSession":
        """Retrieve an existing OAuth2 Authorization Code flow session by state."""
        return OAuth2AuthorizationCodeSession(
            client_id=flask_session["client_id"],
            scopes=flask_session["scopes"],
            target=flask_session["target"],
            state=flask_session["state"],
            provider=self
        )

    def refresh_token(
            self,
            token: CredentialToken,
            *,
            auth: tuple[str, str] | None = None,
            client_id: str | None = None,
            client_secret: str | None = None,
            force=False
    ) -> None:
        """Refresh the access token using the refresh token.

        Args:
            token: The CredentialToken instance to refresh.
            auth: Optional tuple of (username, password) for basic auth.
                Used by Discord
            client_id, client_secret: Client ID and secret.
                Used by Google, GitHub, etc.
            force: If True, force refresh even if the token is not expired.

        auth or client_id/client_secret must be provided, but not both.
        """
        if not token.is_expired() and not force:
            return
        assert "refresh_token" in token.token, "Refresh token not present"
        match (auth, client_id, client_secret):
            case (auth, None, None):
                resp = requests.post(
                    url=self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": token.token["refresh_token"],
                    },
                    headers=self.headers,
                    auth=auth,
                    timeout=TIMEOUT
                )
            case (None, client_id, client_secret):
                # Use client_id and client_secret for token refresh
                resp = requests.post(
                    url=self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": token.token["refresh_token"],
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                    headers=self.headers,
                    timeout=TIMEOUT
                )
            case (None, None, None):
                raise ValueError("Missing auth and client_id/client_secret")
            case (_, _, _):
                raise ValueError(
                    "Provide only auth or client_id/client_secret, not both"
                )
            case _:
                raise ValueError(
                    "Invalid combination of auth, client_id, and client_secret"
                )
        try:
            body = resp.json()
        except Exception as err:
            raise OAuth2SecurityError("Failed to refresh token") from err
        token.refresh_from_response(body)


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
    created_at: schema.DateTime
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
        self.created_at = schema.DateTime.utcnow()
        self.client_id = client_id
        self.response_type = "code"
        self.scopes = scopes
        self.state = state or uid.generate_category_uid("oauthsession")
        self.target = target

    def delete(self) -> None:
        """Delete the session from the database or cache."""
        for key in self.to_dict():
            del flask_session[key]

    def exchange_code_for_token(
            self,
            code: str,
            client_secret: str,
    ) -> dict[str, Any]:
        """Exchange authorization code for access token."""
        logger.info("=== Exchanging authorization code for token ===")

        params = {
            "grant_type": "authorization_code",
            "redirect_uri": self.provider.redirect_uri,
            "client_id": self.client_id,
            "code": code,
            "client_secret": client_secret,
        }

        logger.debug(f"Token exchange URL: {self.provider.token_url}")
        logger.debug(f"Grant type: {params['grant_type']}")
        logger.debug(f"Redirect URI: {params['redirect_uri']}")
        logger.debug(f"Client ID: {params['client_id']}")
        logger.debug(f"Authorization code (first 10 chars): {code[:10]}...")
        logger.debug(f"Client secret (length): {len(client_secret)}")
        logger.debug(f"Request headers: {self.provider.headers}")

        try:
            logger.info(f"Sending POST request to {self.provider.token_url}")
            resp = requests.post(
                self.provider.token_url,
                params=params,
                headers=self.provider.headers,
                timeout=TIMEOUT
            )
            logger.info(f"Token exchange response status: {resp.status_code}")
            logger.debug(f"Response headers: {dict(resp.headers)}")

            # Log the raw response text for debugging
            # First 500 chars
            logger.debug(f"Response text: {resp.text[:500]}")

        except requests.exceptions.Timeout as err:
            logger.error(f"Token exchange request timed out after {TIMEOUT}s")
            raise OAuth2SecurityError(
                "Token exchange request timed out") from err
        except requests.exceptions.RequestException as err:
            logger.error(f"Token exchange request failed: {err}")
            raise OAuth2SecurityError("Token exchange request failed") from err

        try:
            body = resp.json()
            logger.info(
                f"Token exchange response parsed - keys: {list(body.keys())}")
            if "error" in body:
                logger.error(f"Token exchange returned error: {body}")
            else:
                logger.debug(
                    f"Access token received (first 10 chars): {body.get('access_token', '')[:10]}...")
                logger.debug(f"Token type: {body.get('token_type')}")
                logger.debug(f"Expires in: {body.get('expires_in')} seconds")
                logger.debug(f"Scope: {body.get('scope')}")
        except Exception as err:
            logger.error(
                f"Failed to parse token exchange response as JSON: {err}")
            logger.error(
                f"Response status: {resp.status_code}, content: {resp.text[:500]}")
            raise OAuth2SecurityError(
                "Failed to exchange code for token"
            ) from err

        logger.info("=== Token exchange complete ===")
        return body

    def get_authorization_url(self, redirect_uri: Url, **additional_params: str) -> str:
        """Return the authorization URL for redirect, with provider-specific
        params.

        Subclasses should extend this method to implement provider-specific
        logic, such as custom headers or additional parameters.
        """
        logger.debug("=== Constructing authorization URL ===")
        logger.debug(
            f"Provider authorization URL: {self.provider.authorization_url}")
        logger.debug(f"Redirect URI: {redirect_uri}")
        logger.debug(f"Additional params: {additional_params}")

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": self.response_type,
            "scope": " ".join(self.scopes),
            "state": self.state,
            **self.provider.extra_params,
            **additional_params
        }

        logger.debug(f"Final URL params: {params}")
        authorization_url = f"""{self.provider.authorization_url}?{urlencode(params)}"""
        logger.info(
            f"Authorization URL constructed (length: {len(authorization_url)})")

        return authorization_url

    def is_expired(self) -> bool:
        """Check if the session has expired.

        This method checks if the session was created more than 10 minutes ago.
        If so, it considers the session expired.
        """
        return utc_time.is_expired(
            self.created_at.to_datetime(),
            threshold=OAUTH_EXPIRY_MINUTES * 60
        )

    def store(self) -> None:
        """Store the session in the database or cache.

        This method should be implemented by subclasses to persist the session
        data, such as in a database or cache.
        """
        for key, value in self.to_dict().items():
            flask_session[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Return a dictionary representation of the session."""
        return {
            "provider": self.provider.provider,
            "client_id": self.client_id,
            "created_at": self.created_at,
            "response_type": self.response_type,
            "scopes": self.scopes,
            "state": self.state,
            "target": self.target,
        }
