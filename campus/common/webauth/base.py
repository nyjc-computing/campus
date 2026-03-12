"""campus.common.webauth.base

Base configs and models for authentication flows.
"""

__all__ = [
    "SecurityScheme",
]

from typing import Protocol, Type, TypeVar

S = TypeVar("S", bound="SecurityScheme", covariant=True)

SECURITY_PREFERENCE = ("openIdConnect", "oauth2")


class SecurityScheme(Protocol[S]):
    """Web auth model for authentication methods.

    Each authentication method and flow should inherit this subclass and
    implement its own required methods.
    """
    provider: str
    security_scheme: str

    def __init__(self, provider: str):
        """Subclasses must implement an __init__() method that
        initializes the security scheme using keyword arguments.
        Subclasses must also call super().__init__(**kwargs) to ensure
        the base class is properly initialized.
        """
        self.provider = provider
