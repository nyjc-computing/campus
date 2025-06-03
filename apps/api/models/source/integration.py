"""apps/api/models/source/integration.py
Integration Models

This module provides classes for creating and managing Campus integrations,
which are connections to third-party platforms and APIs.
"""
from collections.abc import Mapping
from typing import Literal, NotRequired, TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import BaseRecord, ModelResponse
from common.devops import Env
from common.drum.mongodb import get_drum
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
    # No init required as of now
    pass


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


class IntegrationUpdate(TypedDict, total=False):
    """Request body schema for a integrations.update operation."""
    description: str
    servers: Mapping[Env, Url]
    api_doc: Url  # URL to OpenAPI spec or API documentation
    security: IntegrationAuth
    capabilities: IntegrationCapabilities


class IntegrationNew(IntegrationUpdate):
    """Request body schema for a integrations.new operation.
    
    All fields except name are optional as they are expected to be filled in
    by the admin after the integration is registered.
    """
    name: str  # lowercase, e.g. "google" | "discord" | "github"


class IntegrationResource(IntegrationNew, BaseRecord):
    """Database record schema for an integration.

    This is the internal representation of an integration in the database.
    """
    id: IntegrationID
    enabled: bool  # Whether the integration is enabled in Campus


class Integration:
    """Integration model for handling database operations related to
    integrations.
    """

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def new(self, **fields: Unpack[IntegrationNew]) -> ModelResponse:
        """This registers a new integration.

        This is expected to be an admin operation.
        """
        integration_id = IntegrationID(uid.generate_category_uid("integration", length=8))
        record = IntegrationResource(
            id=integration_id,
            created_at=utc_time.now(),
            enabled=False,  # Default to disabled until configured
            **fields
        )
        resp = self.storage.insert(TABLE, record)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.CREATED, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def delete(self, integration_id: str) -> ModelResponse:
        """Delete an integration by id.
        
        This action is destructive and cannot be undone.
        It should only be done by an admin/owner.
        """
        resp = self.storage.delete_by_id(TABLE, integration_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.DELETED):
                return ModelResponse(**resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Integration not found",
                    id=integration_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def get(self, integration_id: str) -> ModelResponse:
        """Get a circle by id from the circle collection."""
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

    def update(self, circle_id: str, **updates: Unpack[IntegrationUpdate]) -> ModelResponse:
        """Update a circle by id."""
        resp = self.storage.update_by_id(TABLE, circle_id, updates)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")
