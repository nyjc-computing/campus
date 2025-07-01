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
    flow: OAuth2Flow
    _flow_registry: dict[OAuth2Flow, Type[F]] = {}

    def __init__(self, **kwargs: Unpack[OAuth2AuthorizationCodeConfigSchema]):
        super().__init__(**kwargs)
        self.flow = kwargs["flow"]

    @classmethod
    def from_json(cls: Type[F], data: IntegrationConfigSchema) -> F:
        if "oauth2" not in data["security"]:
            raise ValueError(f"Provider {data['name']} does not have oauth2 securty scheme.")
        security_config = data["security"]["oauth2"]
        return cls._flow_registry[security_config["flow"]](**security_config)

    @classmethod
    def register_flow(cls, flow: OAuth2Flow, scheme: Type[F]) -> None:
        """Register an OAuth2 flow."""
        if flow in cls._flow_registry:
            raise ValueError(f"OAuth2 flow {flow} is registered.")
        cls._flow_registry[flow] = scheme

__all__ = [
    "OAuth2AuthorizationCodeConfigSchema",
    "OAuth2FlowScheme",
    "OAuth2SecurityError",
    "OAuth2Flow",
    "OAuth2SecurityError"
]
