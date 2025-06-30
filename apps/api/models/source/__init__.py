"""apps/api/models/source
Source Models

This module provides classes for creating and managing Campus sources, which
are data sources from third-party platforms and APIs.

Data structures:
- collections (Integrations)

Main operations:
- 
"""

from typing import TypedDict, NotRequired, Unpack

from apps.api.models.base import BaseRecord, ModelResponse
from apps.api.errors import api_errors
from common.drum.mongodb import get_db, get_drum
from common.schema import CampusID, Message, Response
from common.utils import uid, utc_time

from .integration import Integration
from .sourcetype import SourceType

SourceID = CampusID

TABLE = "sources"


def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    db = get_db()
    source_meta = db[TABLE].find_one({"@meta": True})
    if source_meta is None:
        db[TABLE].insert_one({
            "@meta": True,
            "integrations": {},
            "sourcetypes": {},
        })


class SourceRecord(BaseRecord, total=False):
    """Schema for a source record in the sources collection."""
    type: str  # Source type (integration.type)
    external_id: str  # Unique ID used by the external platform
    name: str  # Human-friendly name
    description: NotRequired[str]  # Optional description
    linked_by: str  # Circle that linked this source
    linked_at: str  # ISO timestamp
    owner_circles: list[str]  # Owning circles — only these can assign access
    access_policies: dict[str, dict[str, int]]  # Access rules per owning circle
    metadata: NotRequired[dict[str, str]]  # Optional live metadata from the external platform


class SourceNew(TypedDict, total=True):
    """Request body schema for a sources.new operation."""
    type: str
    external_id: str
    name: str
    description: NotRequired[str]
    linked_by: str
    linked_at: str
    owner_circles: list[str]
    access_policies: dict[str, dict[str, int]]
    metadata: NotRequired[dict[str, str]]


class SourceUpdate(TypedDict, total=False):
    """Request body schema for a sources.update operation."""
    name: str
    description: str
    owner_circles: list[str]
    access_policies: dict[str, dict[str, int]]
    metadata: dict[str, str]


class Source:
    """Source model for handling database operations related to sources."""

    def __init__(self):
        """Initialize the Source model with a storage interface."""
        self.storage = get_drum()

    def new(self, **fields: Unpack[SourceNew]) -> ModelResponse:
        """This creates a new source."""
        # TODO: add to circle
        source_id = SourceID(uid.generate_category_uid("source", length=16))
        record = SourceRecord(
            id=source_id,
            created_at=utc_time.now(),
            name=fields["name"],
            description=fields.get("description", ""),
        )
        resp = self.storage.insert(TABLE, record)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.CREATED, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def delete(self, source_id: str) -> ModelResponse:
        """Delete a source by id.
        
        This action is destructive and cannot be undone.
        It should only be done by an admin/owner.
        """
        resp = self.storage.delete_by_id(TABLE, source_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.DELETED):
                return ModelResponse(**resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Source not found",
                    id=source_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def get(self, source_id: str) -> ModelResponse:
        """Get a source by id from the source collection."""
        resp = self.storage.get_by_id(TABLE, source_id)
        # TODO: join with sources and access values
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Source not found",
                    id=source_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")
    
    def list(self) -> ModelResponse:
        """List all sources in the sources collection."""
        resp = self.storage.get_all(TABLE)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                return ModelResponse(status="ok", message=Message.NOT_FOUND, data=[])
        raise ValueError(f"Unexpected response from storage: {resp}")

    def update(self, source_id: str, **updates: Unpack[SourceUpdate]) -> ModelResponse:
        """Update a source by id."""
        resp = self.storage.update_by_id(TABLE, source_id, updates)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Source not found",
                    id=source_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")


__all__ = [
    "Integration",
    "SourceType",
    "init_db",
]
