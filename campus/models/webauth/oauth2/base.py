"""campus.models.webauth.oauth2.base

OAuth2 security scheme base configs and models.
"""

__all__ = ["OAuth2FlowScheme"]

from typing import Generic, Type, TypeVar

from campus.common import integration
from campus.models.webauth import base

# Generic type for OAuth2 flow schemes
F = TypeVar('F', bound='OAuth2FlowScheme')

FLOW_PREFERENCE = ("authorizationCode", "clientCredentials")


class OAuth2FlowScheme(base.SecurityScheme, Generic[F]):
    """OAuth2 security scheme base class for OAuth2 flows."""
    _flow_map: dict[str, Type[F]] = {}
    security_scheme: integration.schema.Security = "oauth2"
    flow: integration.config.OAuth2Flow

    def __init__(self, provider: str):
        super().__init__(provider)

    @classmethod
    def __init_subclass__(cls: Type[F]) -> None:
        """Register subclass in the flow map on definition."""
        cls._flow_map[cls.flow] = cls

    @classmethod
    def from_config(  # type: ignore[override]
            cls: type[F],
            provider: str,
            config: integration.config.OAuth2AuthorizationCodeConfigSchema
    ) -> F:
        """Create an OAuth2FlowScheme instance from config."""
        for flow in FLOW_PREFERENCE:
            if flow in config["flow"]:
                return cls._flow_map[flow].from_config(provider, config)
        raise ValueError("No supported OAuth2 flow found in config.")
