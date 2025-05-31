"""
Integration Models

This module provides classes for managing Campus integrations with third-party
platforms and APIs.

Data structures:
- collections (Integrations)

Main operations:
- 
"""

from collections.abc import Iterator, Mapping
from typing import Final, Literal, NotRequired, TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import BaseRecord, ModelResponse
from common.devops import Env
from common.drum.mongodb import PK, get_db, get_drum
from common.schema import CampusID, Message, Response
from common.utils import uid, utc_time

IntegrationID = CampusID
Url = str

TABLE = "integrations"


# TODO: Refactor settings into a separate model
def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    # Check for existing root circle
    db = get_db()
    integration_meta = db[TABLE].find_one({"@meta": True})
    if (integration_meta is None):
        # Create meta record if it does not exist
        Integration().new()


class IntegrationAuth(TypedDict):
    """Authentication configuration for an integration.

    To be subclassed for each auth type.
    """
    # Follow OpenAPI 3.0 for convenience
    # https://swagger.io/docs/specification/v3_0/authentication/
    type: Literal["http", "apiKey", "oauth2", "openIdConnect"]
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


class IntegrationResource(BaseRecord):
    """Response body schema representing the result of a integrations.get operation."""
    id: IntegrationID
    name: str  # lowercase, e.g. "google" | "discord" | "github"
    description: NotRequired[str]
    servers: Mapping[Env, Url]
    api_doc: NotRequired[Url]  # URL to OpenAPI spec or API documentation
    security: IntegrationAuth
    capabilities: IntegrationCapabilities
    enabled: bool  # Whether the integration is enabled in Campus


