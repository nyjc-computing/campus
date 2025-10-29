"""campus.models.webauth.base

Base configs and models for authentication flows.
"""

__all__ = [
    "SecurityError",
    "SecurityScheme",
]

from typing import Protocol, Type, TypeVar

import campus.integrations as integrations

S = TypeVar("S", bound="SecurityScheme")

SECURITY_PREFERENCE = ("openIdConnect", "oauth2")


class SecurityError(Exception):
    """Base class for security-related errors."""


class SecurityScheme(Protocol[S]):
    """Web auth model for authentication methods.

    Each authentication method and flow should inherit this subclass and
    implement its own required methods.
    """
    _scheme_map: dict[str, Type[S]] = {}
    provider: str
    security_scheme: integrations.config.Security

    def __init__(self, provider: str):
        """Subclasses must implement an __init__() method that
        initializes the security scheme using keyword arguments.
        Subclasses must also call super().__init__(**kwargs) to ensure
        the base class is properly initialized.
        """
        self.provider = provider

    @classmethod
    def __init_subclass__(cls: Type[S]) -> None:
        """Register subclass in the scheme map on definition."""
        cls._scheme_map[cls.security_scheme] = cls

    @classmethod
    def from_provider_config(
        cls: Type[S],
        provider: str,
        config: integrations.config.IntegrationConfigSchema,
        **override_config
    ) -> S:
        """Instantiate a security scheme from a JSON-like dictionary."""
        for security_scheme in SECURITY_PREFERENCE:
            if security_scheme in config["security"]:
                cfg = config.copy()
                cfg.update(override_config)  # type: ignore[typeddict-item]
                return (
                    cls._scheme_map[security_scheme]
                    .from_provider_config(provider, cfg)
                )
        raise ValueError(
            "No supported security scheme found in config."
        )
