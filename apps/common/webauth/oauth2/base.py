"""apps.common.webauth.oauth2.base

OAuth2 security scheme base configs and models.

"""

from typing import Literal, Type, Unpack

from ..base import (
    SecuritySchemeConfigSchema,
    SecurityError,
    SecurityScheme
)

OAuth2Flow = Literal["authorizationCode", "clientCredentials", "implicit", "password"]
Url = str


class OAuth2SecurityError(SecurityError):
    """OAuth2 authentication error."""


class OAuth2ConfigSchema(SecuritySchemeConfigSchema):
    """OAuth2 base authentication schema."""
    flow: OAuth2Flow


class OAuth2FlowScheme(SecurityScheme):
    """OAuth2 security scheme base class for OAuth2 flows.

    OAuth2 is only used for initial authentication of users and clients.
    Subsequent authorization uses HTTP Basic/Bearer schemes.
    """
    flow: OAuth2Flow
    _flow_registry: dict[OAuth2Flow, Type["OAuth2FlowScheme"]] = {}

    def __init__(self, **kwargs: Unpack[OAuth2ConfigSchema]):
        super().__init__(**kwargs)
        self.flow = kwargs["flow"]

    @classmethod
    def from_json(cls, data: OAuth2ConfigSchema) -> "OAuth2FlowScheme":
        if data["security_scheme"] != "oauth2":
            raise ValueError("Invalid security scheme for OAuth2.")
        return cls._flow_registry[data["flow"]](**data)

    @classmethod
    def register_flow(cls, flow: OAuth2Flow, scheme: Type["OAuth2FlowScheme"]) -> None:
        """Register an OAuth2 flow."""
        if flow in cls._flow_registry:
            raise ValueError(f"OAuth2 flow {flow} is registered.")
        cls._flow_registry[flow] = scheme

__all__ = [
    "OAuth2ConfigSchema",
    "OAuth2FlowScheme",
    "OAuth2SecurityError",
    "OAuth2Flow",
    "OAuth2SecurityError"
]
