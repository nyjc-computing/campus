"""campus.integrations.base

Schema to describe the JSON files describing third-party integration
configurations.
"""

from abc import ABC, abstractmethod
import contextlib
from typing import Any, Iterator, Literal, NotRequired, Self, TypedDict

import flask
import werkzeug

from campus.common import schema
from campus.common.devops import Env
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


class SecurityConfigSchema(TypedDict):
    """Schema for security configuration."""
    security_scheme: Security


class OAuth2FlowConfigSchema(SecurityConfigSchema):
    """Schema for OAuth2 flow configuration."""
    flow: OAuth2Flow


class OAuth2AuthorizationCodeConfigSchema(OAuth2FlowConfigSchema):
    """Schema for OAuth2 security configuration."""
    scopes: list[str]
    authorization_url: schema.Url
    token_url: schema.Url
    headers: NotRequired[dict[str, str]]
    user_info_url: schema.Url
    extra_params: NotRequired[dict[str, str]]
    token_params: NotRequired[dict[str, str]]
    user_info_params: NotRequired[dict[str, str]]


class OAuth2ClientCredentialsConfigSchema(OAuth2FlowConfigSchema):
    """Schema for OAuth2 Client Credentials configuration."""
    scopes: list[str]
    token_url: schema.Url
    headers: NotRequired[dict[str, str]]


class IntegrationConfigSchema(TypedDict):
    """Schema for integration configuration."""
    provider: str
    description: str
    servers: dict[Env, schema.Url]
    redirect_uri: str
    api_doc: schema.Url
    discovery_url: schema.Url
    security: dict[Security, SecurityConfigSchema]


class Provider(ABC):
    """Base provider class for OAuth2 integrations.

    This class encapsulates the metadata and core OAuth2 operations
    for a third-party authentication provider.
    """
    provider: str
    title: str
    description: str
    version: str
    openapi_version: str
    authorization_url: schema.Url
    token_url: schema.Url
    security_scheme: webauth.SecurityScheme
    _headers: dict[str, str]
    _token: token.TokenRecord | None = None
    _CLIENT_ID: str
    _CLIENT_SECRET: str

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
        token = tokens.get_by_client_user(self._CLIENT_ID, user_id)
        try:
            yield self.with_token(token)
        finally:
            self.release_token()
