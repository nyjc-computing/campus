"""apps/api/models/source/sourcetype.py
SourceType Models

This module provides classes for creating and managing Campus source types,
which are categories of data sources from third-party platforms and APIs.
"""
from collections.abc import Mapping
from typing import Literal, NotRequired, TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import BaseRecord, ModelResponse
from common.devops import Env
from common.drum.mongodb import get_drum
from common.schema import CampusID, Message, Response
from common.utils import uid, utc_time

from .integration import IntegrationID, IntegrationAuthTypes, Url

SourceTypeID = CampusID

TABLE = "sourcetypes"


# TODO: Refactor settings into a separate model
def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    # No init required as of now
    pass


class SourceTypeUpdate(TypedDict, total=False):
    """Request body schema for a integrations.update operation."""
    description: str
    servers: Mapping[Env, Url]
    api_doc: Url  # URL to OpenAPI spec or API documentation
    security: IntegrationAuthTypes
    scopes: list[str]
    base_url: NotRequired[Url]


class SourceTypeNew(SourceTypeUpdate):
    """Request body schema for a sourcetype.new operation.
    
    All fields except name and integration are optional as they are expected to
    be filled in by the admin after the integration is registered.
    """
    # source type name is lowercase singular,
    # e.g. "form" | "channel" | "repository"
    # the full qualified name is <integration_name>.<source_type_name>
    name: str
    integration: IntegrationID


class SourceTypeResource(SourceTypeNew, BaseRecord):
    """Database record schema for an integration.

    This is the internal representation of an integration in the database.
    """
    id: SourceTypeID
    enabled: bool  # Whether the source type is enabled in Campus


class SourceType:
    """SourceType model for handling database operations related to
    source types.
    """

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def new(self, **fields: Unpack[SourceTypeNew]) -> ModelResponse:
        """This registers a new integration.

        This is expected to be an admin operation.
        """
        integration_id = IntegrationID(uid.generate_category_uid("integration", length=8))
        record = SourceTypeResource(
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

    def update(self, circle_id: str, **updates: Unpack[SourceTypeUpdate]) -> ModelResponse:
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
