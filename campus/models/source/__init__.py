"""apps.common.models.source
Source Models

This module provides classes for creating and managing Campus sources, which
are data sources from third-party platforms and APIs.

Data structures:
- collections (Integrations)

Main operations:
- 
"""

from typing import NotRequired, TypedDict, Unpack

from campus.models.base import BaseRecord
from campus.common.errors import api_errors
from campus.common.utils import uid, utc_time
from campus.common import devops
from campus.storage import get_collection

SourceID = str

TABLE = "sources"


@devops.block_env(devops.PRODUCTION)
def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    pass


class SourceRecord(BaseRecord, total=False):
    """Schema for a source record in the sources collection."""
    type: str  # Source type (integration.type)
    external_id: str  # Unique ID used by the external platform
    name: str  # Human-friendly name
    description: NotRequired[str]  # Optional description
    linked_by: str  # Circle that linked this source
    linked_at: str  # ISO timestamp
    owner_circles: list[str]  # Owning circles — only these can assign access
    # Access rules per owning circle
    access_policies: dict[str, dict[str, int]]
    # Optional live metadata from the external platform
    metadata: NotRequired[dict[str, str]]


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
        self.storage = get_collection(TABLE)

    def new(self, **fields: Unpack[SourceNew]) -> str:
        """This creates a new source."""
        # TODO: add to circle
        source_id = SourceID(uid.generate_category_uid("source", length=16))
        record = SourceRecord(
            id=source_id,
            created_at=utc_time.now(),
            name=fields["name"],
            description=fields.get("description", ""),
            type=fields["type"],
            external_id=fields["external_id"],
            linked_by=fields["linked_by"],
            linked_at=fields["linked_at"],
            owner_circles=fields["owner_circles"],
            access_policies=fields["access_policies"],
            metadata=fields.get("metadata", {}),
        )
        try:
            self.storage.insert_one(dict(record))
            return source_id
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def delete(self, source_id: str) -> None:
        """Delete a source by id.

        This action is destructive and cannot be undone.
        It should only be done by an admin/owner.
        """
        try:
            self.storage.delete_by_id(source_id)
        except Exception as e:
            if isinstance(e, type(api_errors.APIError)) and hasattr(e, 'status_code'):
                raise  # Re-raise API errors as-is
            raise api_errors.InternalError(message=str(e), error=e)

    def get(self, source_id: str) -> dict:
        """Get a source by id from the source collection."""
        try:
            record = self.storage.get_by_id(source_id)
            if record is None:
                raise api_errors.ConflictError(
                    message="Source not found",
                    id=source_id
                )
            return record
        except Exception as e:
            if isinstance(e, type(api_errors.APIError)) and hasattr(e, 'status_code'):
                raise  # Re-raise API errors as-is
            raise api_errors.InternalError(message=str(e), error=e)

    def list(self) -> list[dict]:
        """List all sources in the sources collection."""
        try:
            # Get all documents (excluding metadata documents)
            sources = self.storage.get_matching({"@meta": {"$ne": True}})
            return sources
        except Exception as e:
            raise api_errors.InternalError(message=str(e), error=e)

    def update(self, source_id: str, **updates: Unpack[SourceUpdate]) -> None:
        """Update a source by id."""
        try:
            self.storage.update_by_id(source_id, dict(updates))
        except Exception as e:
            if isinstance(e, type(api_errors.APIError)) and hasattr(e, 'status_code'):
                raise  # Re-raise API errors as-is
            raise api_errors.InternalError(message=str(e), error=e)


__all__ = [
    "init_db",
]
