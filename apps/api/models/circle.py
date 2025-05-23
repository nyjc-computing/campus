"""
Circle Models

This module provides classes for managing Campus circles.
"""

from typing import TypedDict, Unpack

from apps.common.errors import api_errors
from apps.api.models.base import BaseRecord, ModelResponse
from common.drum import PK
from common.drum.mongodb import get_drum
from common.schema import Message, Response

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
    tag: str


class CircleUpdate(TypedDict, total=False):
    """Request body schema for a circles.update operation."""
    name: str
    # tag cannot be updated once created


class CircleResource(CircleNew, BaseRecord, TypedDict, total=True):
    """Response body schema representing the result of a circles.get operation."""


class Circle:
    """Circle model for handling database operations related to circles."""

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def new(self, **fields: Unpack[CircleNew]) -> ModelResponse:
        """Create a new circle."""
        resp = self.storage.insert(
            TABLE,
            fields,
        )
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.CREATED, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def delete(self, circle_id: str) -> ModelResponse:
        """Delete a circle by id."""
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
        """Get a circle by id."""
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
