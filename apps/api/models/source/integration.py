"""apps/api/models/source/integration.py
Integration Models

This module provides classes for creating and managing Campus integrations,
which are connections to third-party platforms and APIs.
"""
from collections.abc import Mapping
from typing import Any, Literal, NotRequired, TypedDict

from apps.api.models.base import ModelResponse
from common.devops import Env
from common.drum.mongodb import get_db
from common.schema import Message

IntegrationAuthTypes = Literal["http", "apiKey", "oauth2", "openIdConnect"]
Url = str

TABLE = "sources"


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


class PollingCapabilities(TypedDict):
    """Polling capabilities of an integration."""
    supported: bool  # Whether polling is supported
    default_poll_interval: NotRequired[int]  # Default polling interval in seconds, if applicable


class WebhookCapabilities(TypedDict):
    """Webhook capabilities of an integration."""
    supported: bool  # Whether the integration supports webhooks
    events: list[str]  # List of events that can trigger webhooks


class CommonCapabilities(TypedDict):
    """Common capabilities of an integration/sourcetype that Campus can use."""
    polling: PollingCapabilities
    webhooks: WebhookCapabilities


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
    capabilities: CommonCapabilities
    enabled: bool  # Whether the integration is enabled in Campus


class IntegrationBase:
    """Abstract base class for integration config objects."""
    def __init__(
            self,
            name: str,
            description: str,
            servers: Mapping[Env, Url],
            api_doc: Url,
            security: Mapping[IntegrationAuthTypes, IntegrationAuth],
            capabilities: CommonCapabilities,
            enabled: bool | None = None
    ):
        self.name = name
        self.description = description
        self.servers = servers
        self.api_doc = api_doc
        self.security = security
        self.capabilities = capabilities
        # Disabled/enabled status is stored in storage
        # Sync from storage on init
        self.enabled = enabled
        self.sync_status()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IntegrationBase":
        """Instantiate from a dict (e.g., loaded from JSON)."""
        return cls(
            name=data["name"],
            description=data["description"],
            servers=data["servers"],
            api_doc=data["api_doc"],
            security=data["security"],
            capabilities=data["capabilities"],
            enabled=data.get("enabled", None)  # Default to False if not present
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "servers": self.servers,
            "api_doc": self.api_doc,
            "security": self.security,
            "capabilities": self.capabilities,
            "enabled": self.enabled
        }

    def disable(self) -> ModelResponse:
        """Disable an integration."""
        self.enabled = False
        self.sync_status()
        return ModelResponse(status="ok", message=Message.SUCCESS)
    
    def enable(self) -> ModelResponse:
        """Enable an integration."""
        self.enabled = True
        self.sync_status()
        return ModelResponse(status="ok", message=Message.SUCCESS)
    
    def sync_status(self) -> ModelResponse:
        """Sync an integration status to storage."""
        db = get_db()
        meta = db[TABLE].find_one({"@meta": True})
        # assume metadata document exists
        if not isinstance(meta, dict):
            raise ValueError("No @meta document found in storage.")
        if not db[TABLE].find_one({
            "@meta": True,
            f"integrations.{self.name}.enabled": {"$exists": True}
        }):
            # Integration not completely registered in storage
            # Default status to False
            # MongoDB $set operator works recursively
            db[TABLE].update_one(
                {"@meta": True},
                {"$set": {f"integrations.{self.name}.enabled": False}}
            )
        integration = db[TABLE].find_one({
            "@meta": True,
            f"integrations.{self.name}": 1
        })
        assert isinstance(integration, dict)
        if self.enabled is None:
            # Instance is inited but not yet synced
            # Set the enabled status from integration doc
            self.enabled = bool(integration["enabled"])
        else:
            # Update storage from instance enabled status
            db[TABLE].update_one(
                {"@meta": True},
                {"$set": {
                    f"integrations.{self.name}.enabled": bool(self.enabled)
                }}
            )
        return ModelResponse(status="ok", message=Message.SUCCESS)
