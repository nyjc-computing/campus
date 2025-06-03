"""apps/api/models/source/integration.py
Integration Models

This module provides classes for creating and managing Campus integrations,
which are connections to third-party platforms and APIs.
"""
from collections.abc import Mapping
from typing import Literal, NotRequired, Required, TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import ModelResponse
from common.devops import Env
from common.drum.mongodb import get_drum
from common.schema import CampusID, Message, Response
from common.utils import uid, utc_time

IntegrationAuthTypes = Literal["http", "apiKey", "oauth2", "openIdConnect"]
IntegrationID = CampusID
Url = str

TABLE = "integrations"


class IntegrationAuth(TypedDict):
    """Authentication configuration for an integration.

    To be subclassed for each auth type.
    """
    # Follow OpenAPI 3.0 for convenience
    # https://swagger.io/docs/specification/v3_0/authentication/
    type: IntegrationAuthTypes
    scopes: list[str]  # OAuth2 scopes that Campus will use


class HttpAuth(IntegrationAuth):
    """HTTP authentication configuration.

    Limited to auth mechanisms supported by Campus, now or in future.
    """
    type: Literal["http"]
    scheme: Literal["bearer"]  # Basic auth not supported


class ApiKeyAuth(IntegrationAuth):
    """API Key authentication configuration."""
    type: Literal["apiKey"]
    in_: Literal["header", "query"]  # Use 'in_' to avoid conflict with Python keyword
    name: str  # Name of the header or query parameter


class OAuth2Auth(IntegrationAuth):
    """OAuth2 authentication configuration."""
    type: Literal["oauth2"]
    flows: Literal["authorizationCode", "clientCredentials", "implicit", "password"]  # implicit and password might be deprecated in future
    authorization_url: NotRequired[str]  # Optional, for user consent flow
    token_url: NotRequired[str]  # Optional, for token exchange


class OpenIdConnectAuth(IntegrationAuth):
    """OpenID Connect authentication configuration."""
    type: Literal["openIdConnect"]
    discovery_url: str  # URL for OpenID Connect discovery document


class IntegrationCapabilities(TypedDict):
    """Capabilities of an integration that Campus can use."""
    webhook_support: bool  # Whether the integration supports webhooks
    webhook_events: list[str]  # List of events that can trigger webhooks
    polling_supported: bool  # Whether the integration supports polling
    default_poll_interval: int  # Default polling interval in seconds


class IntegrationConfig(TypedDict, total=False):
    """Config schema for an integration.

    Since integrations are imported from config and not created or
    mutated via API, they do not have a CampusID or created_at field.
    They are identified via name as the PK.
    """
    name: str  # lowercase, e.g. "google" | "discord" | "github"
    description: str
    servers: Mapping[Env, Url]
    api_doc: Url  # URL to OpenAPI spec or API documentation
    security: Mapping[IntegrationAuthTypes, IntegrationAuth]
    capabilities: IntegrationCapabilities
    enabled: bool  # Whether the integration is enabled in Campus


class Integration:
    """Integration model for handling database operations related to
    integrations.
    """

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def get(self, name: str) -> ModelResponse:
        """Get a circle by id from the circle collection."""
        # TODO: refactor to import from JSON file instead of database
        resp = self.storage.get_by_id(TABLE, integration_id)
        # TODO: join with sources and access values
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=integration_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def disable(self, name: str) -> ModelResponse:
        """Disable an integration."""
        resp = self.storage.update_by_id(
            TABLE,
            integration_id,
            {"$set": {"enabled": False}}
        )
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.SUCCESS, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")
    
    def enable(self, name: str) -> ModelResponse:
        """Enable an integration."""
        resp = self.storage.update_by_id(
            TABLE,
            integration_id,
            {"$set": {"enabled": True}}
        )
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.SUCCESS, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")
    
