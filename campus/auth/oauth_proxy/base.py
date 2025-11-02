"""campus.auth.oauth_proxy.base

Base class for oauth proxies.

An oauth proxy carries out OAuth2 authorization flows with third-party
authentication providers to obtain access tokens for user authentication.
"""

from abc import ABC, abstractmethod
import contextlib
from typing import Iterator, Literal, Self

import werkzeug

from campus.auth import resources
from campus.client.vault import get_vault
from campus.common import schema
from campus.models import token, webauth

HttpScheme = Literal["basic", "bearer"]
OAuth2Flow = Literal[
    "authorizationCode",
    "clientCredentials",
    "implicit",
    "password"
]
Security = Literal[
    "http",
    "apiKey",
    "oauth2",
    "openIdConnect"
]

tokens = token.Tokens()


class AuthProxy(ABC):
    """Base authorization proxy class for OAuth2 integrations.

    This class encapsulates the metadata and core OAuth2 operations
    for a third-party authentication proxy.
    The proxy generates the authorization URL, manages tokens, and
    provides a context manager for authorizing API calls on behalf
    of a user.
    """
    provider: str
    title: str
    description: str
    version: str
    openapi_version: str
    authorization_url: schema.Url
    token_url: schema.Url
    _headers: dict[str, str]
    _token: token.TokenRecord | None = None
    _CLIENT_ID: str
    _CLIENT_SECRET: str

    def __init__(self) -> None:
        vault = get_vault()[self.provider]
        self._CLIENT_ID = vault["CLIENT_ID"].get()['value']
        self._CLIENT_SECRET = vault["CLIENT_SECRET"].get()['value']

    def with_token(self, token: token.TokenRecord) -> Self:
        """A chainable method for passing a token to the instance."""
        self._token = token
        return self

    def release_token(self) -> token.TokenRecord | None:
        """Release the token held by the provider, if any."""
        self._token = None

    @abstractmethod
    def redirect_for_authorization(
            self,
            target: schema.Url,
    ) -> werkzeug.Response:
        """Return a 302 Redirect response to the provider's
        authorization URL.
        """

    @contextlib.contextmanager
    def authorize_for_user(
            self: Self,
            user_id: schema.UserID
    ) -> Iterator[Self]:
        """Context manager to authorize a user API use."""
        credentials = resources.credentials.find_credentials(
            self.provider,
            user_id
        )  # type: ignore[var-annotated]
        token = credentials.token
        try:
            yield self.with_token(token)
        finally:
            self.release_token()
