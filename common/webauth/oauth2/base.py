"""common.webauth.oauth2.base

OAuth2 security scheme base configs and models.

"""

from typing import Generic, Literal, Type, TypeVar, Unpack

from common.integration.config import (
    IntegrationConfigSchema,
    OAuth2AuthorizationCodeConfigSchema,
)

from ..base import (
    SecurityError,
    SecurityScheme
)

# Generic type for OAuth2 flow schemes
F = TypeVar('F', bound='OAuth2FlowScheme')
Url = str

OAuth2Flow = Literal["authorizationCode", "clientCredentials", "implicit", "password"]


class OAuth2InvalidRequestError(SecurityError):
    """OAuth2 invalid request error."""


class OAuth2SecurityError(SecurityError):
    """OAuth2 authentication error."""


class OAuth2FlowScheme(SecurityScheme, Generic[F]):
    """OAuth2 security scheme base class for OAuth2 flows.

    OAuth2 is only used for initial authentication of users and clients.
    Subsequent authorization uses HTTP Basic/Bearer schemes.
    """
    flow: str

    def __init__(
            self,
            provider: str,
            **config: Unpack[OAuth2AuthorizationCodeConfigSchema]
    ):
        super().__init__(provider, **config)
        self.flow = config["flow"]


__all__ = [
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2FlowScheme",
    "OAuth2SecurityError",
    "OAuth2Flow",
    "OAuth2SecurityError"
]
