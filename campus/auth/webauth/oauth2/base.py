"""campus.auth.webauth.oauth2.base

OAuth2 security scheme base configs and models.
"""

__all__ = ["OAuth2FlowScheme"]

from typing import Generic, Type, TypeVar

from .. import base

# Generic type for OAuth2 flow schemes
F = TypeVar('F', bound='OAuth2FlowScheme')

FLOW_PREFERENCE = ("authorizationCode", "clientCredentials")


class OAuth2FlowScheme(base.SecurityScheme, Generic[F]):
    """OAuth2 security scheme base class for OAuth2 flows."""
    _flow_map: dict[str, Type[F]] = {}
    security_scheme = "oauth2"
    flow: str

    def __init__(self, provider: str):
        super().__init__(provider)
