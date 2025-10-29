"""campus.integrations.base

Schema to describe the JSON files describing third-party integration
configurations.
"""

from typing import Literal, NotRequired, TypedDict

from campus.common import schema
from campus.common.devops import Env

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
