"""campus.auth.webauth.oauth2.authorization_code

OAuth2 Authorization Code flow schemas and models.

Reference: https://datatracker.ietf.org/doc/html/rfc6749#section-4.1
"""

__all__ = ["OAuth2AuthorizationCodeFlowScheme"]

from typing import Any

import requests

from campus.common import schema
from campus.common.errors import auth_errors, token_errors
from campus.common.utils import url
import campus.model

from . import base
from ... import resources

# Default expiry time for OAuth2 sessions in minutes
OAUTH_EXPIRY_MINUTES = 10
# Default timeout for requests in seconds
TIMEOUT = 10


class OAuth2AuthorizationCodeFlowScheme(base.OAuth2FlowScheme):
    """Configures OAuth2 Authorization Code flow for a specified
    provider (google, github, discord, ...).

    The attributes are typically provided from a config file.
    """
    flow = "authorizationCode"
    authorization_url: schema.Url
    token_url: schema.Url
    redirect_uri: schema.Url
    headers: dict[str, str]
    user_info_url: schema.Url | None
    scopes: list[str]

    def __init__(
            self,
            provider: str,
            client_id: str,
            redirect_uri: schema.Url,
            authorization_url: schema.Url,
            token_url: schema.Url,
            scopes: list[str],
            headers: dict[str, str] | None = None,
            user_info_url: schema.Url | None = None,
    ):
        super().__init__(provider)
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.authorization_url = authorization_url
        self.token_url = token_url
        self.scopes = scopes
        self.headers = headers or {}
        self.user_info_url = user_info_url

    def exchange_code_for_token(
            self,
            code: str,
            client_id: schema.CampusID,
            client_secret: str,
    ) -> campus.model.OAuthToken:
        """Exchange authorization code for access token."""
        authsession = resources.session[self.provider].get(code)
        if authsession.provider != self.provider:
            raise auth_errors.ServerError(
                "Provider mismatch",
                session_provider=authsession.provider,
                host_provider=self.provider
            )
        if authsession.client_id != client_id:
            raise auth_errors.ServerError(
                "Client ID mismatch during token exchange.",
                session_client_id=authsession.client_id,
                provided_client_id=client_id
            )
        params = {
            "grant_type": "authorization_code",
            "redirect_uri": authsession.redirect_uri,
            "client_id": authsession.client_id,
            "code": code,
            "client_secret": client_secret,
        }
        request_time = schema.DateTime.utcnow()
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
            token_errors.raise_from_json(token_payload)
        return campus.model.OAuthToken(
            id=token_payload["access_token"],
            created_at=request_time,
            expiry_seconds=token_payload["expires_in"],
            refresh_token=token_payload["refresh_token"],
            scopes=token_payload["scope"].split(" "),
        )

    def get_authorization_url(
            self,
            state: str,
            **add_params: str
    ) -> schema.Url:
        """Return the authorization URL for redirect, with
        provider-specific params.

        Subclasses should extend this method to implement
        provider-specific logic, such as custom headers or additional
        parameters.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            **add_params
        }
        authorization_url = url.create_url(
            hostname=self.authorization_url,
            params=params
        )
        return schema.Url(authorization_url)

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch user info from the provider's user info endpoint."""
        if not self.user_info_url:
            return {}
        headers = {
            **self.headers,
            "Authorization": f"Bearer {access_token}",
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

    def refresh_token(
            self,
            auth_token: campus.model.OAuthToken,
            *,
            auth: tuple[str, str] | None = None,
            client_id: str,
            client_secret: str | None = None,
            force=False
    ) -> campus.model.OAuthToken:
        """Refresh the access token using the refresh token if present,
        otherwise retrieve a new token.

        Args:
            token: The CredentialToken instance to refresh.
            auth: Optional tuple of (username, password) for basic auth.
                Used by Discord
            client_id, client_secret: Client ID and secret.
                Used by Google, GitHub, etc.
            force: If True, force refresh even if the token is not
                expired.

        auth or client_id/client_secret must be provided, but not both.
        """
        # Only pass auth or client_id/client_secret, not both
        if auth and (client_id or client_secret):
            raise ValueError(
                "Provide only auth or client_id/client_secret, not both"
            )
        if not auth_token.is_expired() and not force:
            return auth_token
        if not auth_token.refresh_token:
            raise token_errors.UnsupportedGrantTypeError(
                "No refresh token available; cannot refresh token"
            )
        if auth:
            token_payload = self._refresh_with_auth(
                auth_token,
                auth=auth
            )
        else:  # client credentials
            if not client_id or not client_secret:
                raise ValueError(
                    "client_id and client_secret must be provided"
                )
            token_payload = self._refresh_with_credentials(
                auth_token,
                client_id=client_id,
                client_secret=client_secret
            )
        if "error" in token_payload:
            token_errors.raise_from_json(token_payload)
        auth_token = campus.model.OAuthToken.from_resource(token_payload)
        # auth_token = token.TokenRecord.from_dict(token_payload)
        credentials = resources.credentials[self.provider].get(auth_token.id)
        if credentials.client_id != client_id:
            raise token_errors.InvalidClientError(
                "Client ID mismatch during token refresh.",
                credential_client_id=credentials.client_id,
                provided_client_id=client_id
            )
        resources.credentials[self.provider][credentials.user_id].update(
            client_id=client_id,
            token=auth_token
        )
        return auth_token

    def _refresh_with_auth(
            self,
            auth_token: campus.model.OAuthToken,
            *,
            auth: tuple[str, str]
    ) -> dict[str, Any]:
        """Send a POST request with the given auth token."""
        resp = requests.post(
            url=self.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": auth_token.refresh_token,
            },
            headers=self.headers,
            auth=auth,
            timeout=TIMEOUT
        )
        token_payload = resp.json()
        return token_payload

    def _refresh_with_credentials(
            self,
            auth_token: campus.model.OAuthToken,
            *,
            client_id: str,
            client_secret: str
    ) -> dict[str, Any]:
        """Send a POST request with the given client credentials."""
        resp = requests.post(
            url=self.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": auth_token.refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers=self.headers,
            timeout=TIMEOUT
        )
        token_payload = resp.json()
        return token_payload
