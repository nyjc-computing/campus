"""common.webauth.base

Base configs and models for authentication flows.
"""

from typing import Literal, Protocol, Required, Type, TypeVar, TypedDict, Unpack

from common.integration.config import IntegrationConfigSchema

S = TypeVar("S", bound="SecurityScheme")

Security = Literal["http", "apiKey", "oauth2", "openIdConnect"]


class SecurityError(Exception):
    """Base class for security-related errors."""


class SecuritySchemeConfigSchema(TypedDict, total=False):
    """Generalized authentication configuration.
    
    This base class defines a common schema for HTTP, API Key, OAuth2, and
    OpenID Connect security schemes.
    The schema follows OpenAPI 3.0 for convenience
    https://swagger.io/docs/specification/v3_0/authentication/
    """
    security_scheme: Required[Security]


class SecurityScheme(Protocol):
    """Web auth model for authentication methods.

    Each authentication method and flow should inherit this subclass and
    implement its own required methods.
    """
    provider: str
    security_scheme: Security
    scopes: list[str]

    def __init__(self, provider: str, **config: Unpack[SecuritySchemeConfigSchema]):
        """Subclasses must implement an __init__() method that initializes the
        security scheme using keyword arguments.
        Subclasses must also call super().__init__(**kwargs) to ensure
        the base class is properly initialized.
        """
        self.provider = provider
        self.security_scheme = config["security_scheme"]

    @classmethod
    def from_json(
            cls: Type[S],
            data: IntegrationConfigSchema,
            security: Security
        ) -> S:
        """Instantiate a security scheme from a JSON-like dictionary."""
        if security not in data["security"]:
            raise ValueError(
                f"Integration {data['provider']} does not have {security} security configured."
            )
        provider = data["provider"]
        security_config = data["security"][security]
        return cls(provider, **security_config)


__all__ = [
    "SecuritySchemeConfigSchema",
    "Security",
    "SecurityError",
    "SecurityScheme",
]
