"""campus.auth.oauth_proxy.base

Base class for oauth proxies.

An oauth proxy carries out OAuth2 authorization flows with third-party
authentication providers to obtain access tokens for user authentication.
"""

from abc import ABC, abstractmethod
import contextlib
from typing import Iterator, Literal, Self

import werkzeug

from campus.common import schema
import campus.model

from .. import resources

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
    _token: campus.model.OAuthToken | None = None
    _CLIENT_ID: str
    _CLIENT_SECRET: str

    def __init__(self) -> None:
        self._CLIENT_ID = resources.vault[self.provider]["CLIENT_ID"]
        self._CLIENT_SECRET = resources.vault[self.provider]["CLIENT_SECRET"]

    @property
    @abstractmethod
    def authorization_url(self) -> schema.Url: ...

    @property
    @abstractmethod
    def token_url(self) -> schema.Url: ...

    @property
    @abstractmethod
    def user_info_url(self) -> schema.Url | None: ...

    @property
    @abstractmethod
    def headers(self) -> dict[str, str]: ...

    @property
    @abstractmethod
    def scopes(self) -> list[str]: ...

    def with_token(self, token: campus.model.OAuthToken) -> Self:
        """A chainable method for passing a token to the instance."""
        self._token = token
        return self

    def release_token(self) -> campus.model.OAuthToken:
        """Release the token held by the provider, if any."""
        token = self._token
        if token is None:
            raise RuntimeError("No token loaded.")
        self._token = None
        return token

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
        credentials = (
            resources.credentials[self.provider][user_id].get(self._CLIENT_ID)
        )
        token = credentials.token
        try:
            yield self.with_token(token)
        finally:
            self.release_token()
