"""campus.models.webauth.oauth2.base

OAuth2 security scheme base configs and models.
"""

__all__ = ["OAuth2FlowScheme"]

from typing import Any, Generic, Type, TypeVar

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
            config: dict[str, Any]
    ) -> F:
        """Create an OAuth2FlowScheme instance from config."""
        assert provider == config["provider"]
        for flow in FLOW_PREFERENCE:
            for scheme_cfg in config["security"].values():
                if (
                        scheme_cfg["security_scheme"] == "oauth2"
                        and scheme_cfg["flow"] == flow
                ):
                    return cls._flow_map[flow].from_config(provider,
                                                           scheme_cfg)
        raise ValueError("No supported OAuth2 flow found in config.")
