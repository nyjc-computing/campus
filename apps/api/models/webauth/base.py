"""apps/api/models/auth/authentication/base

Base configs and models for authentication flows.
"""

from typing import Literal, Protocol, Required, Type, TypedDict, Unpack

Security = Literal["http", "apiKey", "oauth2", "openIdConnect"]


class SecurityError(Exception):
    """Base class for security-related errors."""


class HttpHeader(TypedDict):
    """HTTP header for authentication."""
    Authorization: str


class SecuritySchemeConfigSchema(TypedDict, total=False):
    """Generalized authentication configuration.
    
    This base class defines a common schema for HTTP, API Key, OAuth2, and
    OpenID Connect security schemes.
    The schema follows OpenAPI 3.0 for convenience
    https://swagger.io/docs/specification/v3_0/authentication/
    """
    security_scheme: Required[Security]
    scopes: Required[list[str]]


class SecurityScheme(Protocol):
    """Web auth model for authentication methods.

    Each authentication method and flow should inherit this subclass and
    implement its own required methods.
    """
    security_scheme: Security
    scopes: list[str]
    _registry: dict[Security, Type["SecurityScheme"]] = {}

    def __init__(self, **kwargs: Unpack[SecuritySchemeConfigSchema]):
        """Subclasses must implement an __init__() method that initializes the
        security scheme using keyword arguments.
        Subclasses must also call super().__init__(**kwargs) to ensure
        the base class is properly initialized.
        """
        self.security_scheme = kwargs["security_scheme"]
        self.scopes = kwargs["scopes"]

    @classmethod
    def from_json(cls, data) -> "SecurityScheme":
        """Instantiate a security scheme from a JSON-like dictionary."""
        if data["security_scheme"] not in cls._registry:
            raise ValueError(f"Security scheme {data['security_scheme']} is not registered.")
        return cls._registry[data["security_scheme"]](**data)

    @classmethod
    def register(cls, security: Security, scheme: Type["SecurityScheme"]) -> None:
        """Register a security scheme class for a given security type."""
        if security in cls._registry:
            raise ValueError(f"Security scheme for {security} is registered.")
        cls._registry[security] = scheme


__all__ = [
    "SecuritySchemeConfigSchema",
    "HttpHeader",
    "Security",
    "SecurityError",
    "SecurityScheme",
]
