"""apps.common.models.integration.config.schema

Schema to describe the JSON files describing third-party integration
configurations.
"""

from typing import Literal, NotRequired, TypedDict

from campus.common.devops import Env

HttpScheme = Literal["basic", "bearer"]
OAuth2Flow = Literal["authorizationCode", "clientCredentials", "implicit", "password"]
Security = Literal["http", "apiKey", "oauth2", "openIdConnect"]

Url = str


class SecurityConfigSchema(TypedDict):
    """Schema for security configuration."""
    security_scheme: Security


class OAuth2AuthorizationCodeConfigSchema(SecurityConfigSchema):
    """Schema for OAuth2 security configuration."""
    flow: str
    scopes: list[str]
    authorization_url: Url
    token_url: Url
    headers: NotRequired[dict[str, str]]
    user_info_url: Url
    extra_params: NotRequired[dict[str, str]]
    token_params: NotRequired[dict[str, str]]
    user_info_params: NotRequired[dict[str, str]]


class IntegrationConfigSchema(TypedDict):
    """Schema for integration configuration."""
    provider: str
    description: str
    servers: dict[Env, Url]
    redirect_uri: str
    api_doc: Url
    discovery_url: Url
    security: dict[Security, SecurityConfigSchema]
