"""apps.common.webauth.base

Base configs and models for authentication flows.
"""

from typing import Protocol, Type, TypeVar, Unpack

from common.integration.config import (
    Security,
    IntegrationConfigSchema,
    SecurityConfigSchema
)

S = TypeVar("S", bound="SecurityScheme")


class SecurityError(Exception):
    """Base class for security-related errors."""


class SecurityScheme(Protocol):
    """Web auth model for authentication methods.

    Each authentication method and flow should inherit this subclass and
    implement its own required methods.
    """
    provider: str
    security_scheme: Security

    def __init__(self, provider: str, **config: Unpack[SecurityConfigSchema]):
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
    "SecurityError",
    "SecurityScheme",
]
