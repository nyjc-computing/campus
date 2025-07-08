"""apps.common.models.integration

This module provides classes for creating and managing Campus integrations,
which are connections to third-party platforms and APIs.
"""

from collections.abc import Mapping
from typing import Any, NotRequired, TypedDict

from common.devops import Env
from storage import get_collection

from . import config, schema

from .config import Security, IntegrationConfigSchema, SecurityConfigSchema, get_config

Url = str

COLLECTION = "integrations"

__all__ = [
    "get_config",
]


# TODO: Refactor settings into a separate model
def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    # Initialize the collection (creates it if needed)
    storage = get_collection(COLLECTION)
    storage.init_collection()

    # Ensure meta record exists
    meta_list = storage.get_matching({"@meta": True})
    if not meta_list:
        storage.insert_one({"@meta": True})
        meta_list = storage.get_matching({"@meta": True})
    meta_record = meta_list[0]


class PollingCapabilities(TypedDict):
    """Polling capabilities of an integration."""
    supported: bool  # Whether polling is supported
    # Default polling interval in seconds, if applicable
    default_poll_interval: NotRequired[int]


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
    security: Mapping[Security, SecurityConfigSchema]
    capabilities: CommonCapabilities
    enabled: bool  # Whether the integration is enabled in Campus


class Integration:
    """Encapsulate integration properties and interactions."""

    def __init__(
            self,
            provider: str,
            description: str,
            servers: Mapping[Env, Url],
            api_doc: Url,
            security: Mapping[Security, SecurityConfigSchema],
            capabilities: CommonCapabilities,
            enabled: bool | None = None
    ):
        self.provider = provider
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
    def from_dict(cls, data: dict[str, Any]) -> "Integration":
        """Instantiate from a dict (e.g., loaded from JSON)."""
        return cls(
            provider=data["provider"],
            description=data["description"],
            servers=data["servers"],
            api_doc=data["api_doc"],
            security=data["security"],
            capabilities=data["capabilities"],
            # Default to False if not present
            enabled=data.get("enabled", None)
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "provider": self.provider,
            "description": self.description,
            "servers": self.servers,
            "api_doc": self.api_doc,
            "security": self.security,
            "capabilities": self.capabilities,
            "enabled": self.enabled
        }

    def disable(self):
        """Disable an integration."""
        self.enabled = False
        self.sync_status()

    def enable(self):
        """Enable an integration."""
        self.enabled = True
        self.sync_status()

    def sync_status(self):
        """Sync an integration status to storage."""
        storage = get_collection(COLLECTION)
        meta_list = storage.get_matching({"@meta": True})
        if not meta_list:
            raise ValueError("No @meta document found in storage.")
        meta_record = meta_list[0]
        if not "enabled" in meta_record["integrations"][self.provider]:
            # If the integration is not registered, register it
            storage.update_matching(
                {"@meta": True},
                {f"integrations.{self.provider}.enabled": False}
            )

        integration = storage.get_matching({
            "@meta": True,
            f"integrations.{self.provider}": 1
        })[0]
        assert isinstance(integration, dict) and "enabled" in integration
        if self.enabled is None:
            # Instance is inited but not yet synced
            # Set the enabled status from integration doc
            self.enabled = bool(integration["enabled"])
        else:
            # Update storage from instance enabled status
            storage.update_matching(
                {"@meta": True},
                {f"integrations.{self.provider}.enabled": bool(self.enabled)}
            )


class IntegrationCredentials(TypedDict):
    """Credentials for an integration."""
    client_id: str
    client_secret: str
    access_token: NotRequired[str]  # Optional access token for OAuth2 flows
    refresh_token: NotRequired[str]  # Optional refresh token for OAuth2 flows
