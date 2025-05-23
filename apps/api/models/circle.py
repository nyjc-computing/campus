"""
Circle Models

This module provides classes for managing Campus circles.
"""

from typing import NotRequired, TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import BaseRecord, ModelResponse
from common.drum.mongodb import get_drum
from common.schema import CampusID, UserID, Message, Response
from common.utils import uid, utc_time

TABLE = "circles"


def init_db():
    """Initialize the collections needed by the model.

    This function is intended to be called only in a test environment or
    staging.
    For MongoDB, collections are created automatically on first insert.
    """
    # No-op for MongoDB, but you could create indexes here if needed.


class CircleNew(TypedDict, total=True):
    """Request body schema for a circles.new operation."""
    name: str
    description: NotRequired[str]
    tag: str
    parents: list[]


class CircleUpdate(TypedDict, total=False):
    """Request body schema for a circles.update operation."""
    name: str
    description: str
    # tag cannot be updated once created


class CircleRecord(CircleNew, BaseRecord, TypedDict, total=True):
    """The circle record stored in the circle collection."""


class CircleResource(CircleRecord, TypedDict, total=True):
    """Response body schema representing the result of a circles.get operation."""


class Circle:
    """Circle model for handling database operations related to circles."""

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def new(self, **fields: Unpack[CircleNew]) -> ModelResponse:
        """This creates a new circle and adds it to the circle collection.

        It does not add it to the circle hierarchy or access control.
        """
        circle_id = uid.generate_category_uid("circle", length=8)
        record = CircleResource(
            id=circle_id,
            created_at=utc_time.now(),
            **fields,
        )
        resp = self.storage.insert(TABLE, record)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.CREATED, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def delete(self, circle_id: str) -> ModelResponse:
        """Delete a circle by id.
        
        This action is destructive and cannot be undone.
        It should only be done by an admin/owner.
        """
        resp = self.storage.delete_by_id(TABLE, circle_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.DELETED):
                return ModelResponse(**resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def get(self, circle_id: str) -> ModelResponse:
        """Get a circle by id from the circle collection."""
        resp = self.storage.get_by_id(TABLE, circle_id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=circle_id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def update(self, circle_id: str, **updates: Unpack[CircleUpdate]) -> ModelResponse:
        """Update a circle by id."""
        resp = self.storage.update_by_id('circles', circle_id, updates)
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
