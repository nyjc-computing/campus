"""campus.models.webauth.oauth2.authorization_code

OAuth2 Authorization Code flow schemas and models.
"""

__all__ = ["OAuth2AuthorizationCodeFlowScheme"]

from typing import Any

import requests

from campus.common import integration, schema
from campus.common.errors import auth_errors, token_errors
from campus.common.utils import url
from campus.models import session, token

from .base import (
    OAuth2FlowScheme,
)

OAUTH_EXPIRY_MINUTES = 10  # Default expiry time for OAuth2 sessions in minutes
TIMEOUT = 10  # Default timeout for requests in seconds

tokens = token.Tokens()


class OAuth2AuthorizationCodeFlowScheme(OAuth2FlowScheme):
    """Configures OAuth2 Authorization Code flow for a specified provider
    (google, github, discord, ...).

    The attributes are typically provided from a config file.
    """
    flow: integration.config.OAuth2Flow = "authorizationCode"
    authorization_url: schema.Url
    token_url: schema.Url
    redirect_uri: schema.Url
    headers: dict[str, str]
    user_info_url: schema.Url | None
    extra_params: dict[str, str]
    token_params: dict[str, str]
    user_info_params: dict[str, str]
    scopes: list[str]

    def __init__(
            self,
            provider: str,
            authorization_url: schema.Url,
            token_url: schema.Url,
            scopes: list[str],
            headers: dict[str, str] | None = None,
            user_info_url: schema.Url | None = None,
            extra_params: dict[str, str] | None = None,
            token_params: dict[str, str] | None = None,
            user_info_params: dict[str, str] | None = None,
    ):
        super().__init__(provider)
        self.authorization_url = authorization_url
        self.token_url = token_url
        self.scopes = scopes
        self.headers = headers or {}
        self.user_info_url = user_info_url
        self.extra_params = extra_params or {}
        self.token_params = token_params or {}
        self.user_info_params = user_info_params or {}
        self._auth = session.AuthSessions(self.provider)
        self._session: session.AuthSessionRecord | None = None

    @classmethod
    def from_config(
            cls: type["OAuth2AuthorizationCodeFlowScheme"],
            provider: str,
            config: dict[str, Any]
    ) -> "OAuth2AuthorizationCodeFlowScheme":
        """Create an OAuth2AuthorizationCodeFlowScheme instance from
        config.
        """
        return cls(
            provider=provider,
            authorization_url=config["authorization_url"],
            token_url=config["token_url"],
            scopes=config["scopes"],
            headers=config.get("headers", {}),
            user_info_url=config["user_info_url"],
            extra_params=config.get("extra_params", {}),
            token_params=config.get("token_params", {}),
            user_info_params=config.get("user_info_params", {}),
        )

    @property
    def auth_session(self) -> session.AuthSessionRecord:
        if self._session is None:
            raise ValueError("Session not initialized")
        return self._session

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
        userinfo_payload = resp.json()
        if "error" in userinfo_payload:
            auth_errors.raise_from_json(userinfo_payload)
        return userinfo_payload

    def init_session(
            self,
            *,
            redirect_uri: schema.Url,
            user_id: schema.UserID | None = None,
            client_id: str,
            scopes: list[str],
            target: schema.Url | None = None,
    ) -> session.AuthSessionRecord:
        """Create a new OAuth2 Authorization Code flow session.
        Revokes any existing session for the user.
        Note that this sets session_id in client-side cookie.

        Returns the session.
        """
        self._session = self._auth.new(
            expiry_seconds=OAUTH_EXPIRY_MINUTES * 60,
            redirect_uri=redirect_uri,
            client_id=client_id,
            user_id=user_id,
            scopes=scopes,
            target=target,
        )
        return self.auth_session

    def retrieve_session(self) -> session.AuthSessionRecord:
        """Retrieve an existing OAuth2 Authorization Code flow session.

        Args:
            session_id: The session ID to retrieve.
            override: If True, override any existing session.
        """
        auth_session = self._auth.get()
        self._session = auth_session
        return self.auth_session

    def exchange_code_for_token(
            self,
            code: str,
            client_secret: str,
            redirect_uri: schema.Url,
    ) -> token.TokenRecord:
        """Exchange authorization code for access token."""
        params = {
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "client_id": self.auth_session.client_id,
            "code": code,
            "client_secret": client_secret,
        }
        try:
            # TODO: retry logic for transient errors
            resp = requests.post(
                self.token_url,
                params=params,
                headers=self.headers,
                timeout=TIMEOUT
            )
        except requests.exceptions.Timeout as err:
            raise auth_errors.TemporarilyUnavailableError(
                "Token exchange request timed out"
            ) from None
        token_payload = resp.json()
        if "error" in token_payload:
            token_errors.raise_from_error(
                token_payload["error"],
                token_payload.get("error_description"),
                token_payload.get("error_uri")
            )
        return token.TokenRecord.from_dict(token_payload)

    def get_authorization_url(
            self,
            redirect_uri: schema.Url,
            **additional_params: str
    ) -> schema.Url:
        """Return the authorization URL for redirect, with provider-specific
        params.

        Subclasses should extend this method to implement provider-specific
        logic, such as custom headers or additional parameters.
        """
        params = {
            "client_id": self.auth_session.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": self.auth_session.id,
            **self.extra_params,
            **additional_params
        }
        authorization_url = url.create_url(
            hostname=self.authorization_url,
            params=params
        )
        return schema.Url(authorization_url)

    # def get_token(
    #         self,
    #         *,
    #         auth: tuple[str, str] | None = None,
    #         client_id: str | None = None,
    #         client_secret: str | None = None
    # ) -> token.TokenRecord:
    #     """Retrieve access token using client credentials.

    #     Args:
    #         auth: Optional tuple of (username, password) for basic auth.
    #             Used by Discord
    #         client_id, client_secret: Client ID and secret.
    #             Used by Google, GitHub, etc.
    #     """
    #     # TODO: refactor into client_credentials submodule
    #     # Only pass auth or client_id/client_secret, not both
    #     if auth and (client_id or client_secret):
    #         raise ValueError(
    #             "Provide only auth or client_id/client_secret, not both"
    #         )
    #     if auth:
    #         resp = requests.post(
    #             url=self.token_url,
    #             data={
    #                 "grant_type": "client_credentials",
    #             },
    #             headers=self.headers,
    #             auth=auth,
    #             timeout=TIMEOUT
    #         )
    #     else:  # client credentials
    #         if not client_id or not client_secret:
    #             raise ValueError(
    #                 "client_id and client_secret must be provided"
    #             )
    #         resp = requests.post(
    #             url=self.token_url,
    #             data={
    #                 "grant_type": "client_credentials",
    #                 "client_id": client_id,
    #                 "client_secret": client_secret,
    #             },
    #             headers=self.headers,
    #             timeout=TIMEOUT
    #         )
    #     token_payload = resp.json()
    #     if "error" in token_payload:
    #         token_errors.raise_from_json(token_payload)
    #     return token.TokenRecord.from_dict(token_payload)

    # def refresh_token(
    #         self,
    #         auth_token: token.TokenRecord,
    #         *,
    #         auth: tuple[str, str] | None = None,
    #         client_id: str | None = None,
    #         client_secret: str | None = None,
    #         force=False
    # ) -> token.TokenRecord:
    #     """Refresh the access token using the refresh token if present,
    #     otherwise retrieve a new token.

    #     Args:
    #         token: The CredentialToken instance to refresh.
    #         auth: Optional tuple of (username, password) for basic auth.
    #             Used by Discord
    #         client_id, client_secret: Client ID and secret.
    #             Used by Google, GitHub, etc.
    #         force: If True, force refresh even if the token is not expired.

    #     auth or client_id/client_secret must be provided, but not both.
    #     """
    #     # Only pass auth or client_id/client_secret, not both
    #     if auth and (client_id or client_secret):
    #         raise ValueError(
    #             "Provide only auth or client_id/client_secret, not both"
    #         )
    #     if not auth_token.is_expired() and not force:
    #         return auth_token
    #     if not auth_token.refresh_token:
    #         return self.get_token(
    #             auth=auth,
    #             client_id=client_id,
    #             client_secret=client_secret
    #         )
    #     if auth:
    #         resp = requests.post(
    #             url=self.token_url,
    #             data={
    #                 "grant_type": "refresh_token",
    #                 "refresh_token": auth_token.refresh_token,
    #             },
    #             headers=self.headers,
    #             auth=auth,
    #             timeout=TIMEOUT
    #         )
    #     else:  # client credentials
    #         if not client_id or not client_secret:
    #             raise ValueError(
    #                 "client_id and client_secret must be provided"
    #             )
    #         resp = requests.post(
    #             url=self.token_url,
    #             data={
    #                 "grant_type": "refresh_token",
    #                 "refresh_token": auth_token.refresh_token,
    #                 "client_id": client_id,
    #                 "client_secret": client_secret,
    #             },
    #             headers=self.headers,
    #             timeout=TIMEOUT
    #         )
    #     token_payload = resp.json()
    #     if "error" in token_payload:
    #         token_errors.raise_from_json(token_payload)
    #     auth_token = token.TokenRecord.from_dict(token_payload)
    #     tokens.update(auth_token)
    #     return auth_token
