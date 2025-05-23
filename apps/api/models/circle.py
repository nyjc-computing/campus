"""
Circle Models

This module provides classes for managing Campus circles.
"""

from apps.common.errors import api_errors
from apps.api.models.base import ModelResponse
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


class Circle:
    """Circle model for handling database operations related to circles."""

    def __init__(self):
        """Initialize the Circle model with a storage interface."""
        self.storage = get_drum()

    def new(self, id: str, name: str, tag: str) -> ModelResponse:
        """Create a new circle."""
        resp = self.storage.insert(
            TABLE,
            {PK: id, "name": name, "tag": tag}
        )
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.SUCCESS):
                return ModelResponse(status="ok", message=Message.CREATED, data=resp.data)
        raise ValueError(f"Unexpected response from storage: {resp}")

    def delete(self, id: str) -> ModelResponse:
        """Delete a circle by id."""
        resp = self.storage.delete_by_id(TABLE, id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.DELETED):
                return ModelResponse(**resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def get(self, id: str) -> ModelResponse:
        """Get a circle by id."""
        resp = self.storage.get_by_id(TABLE, id)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")

    def update(self, id: str, updates: dict) -> ModelResponse:
        """Update a circle by id."""
        resp = self.storage.update_by_id('circles', id, updates)
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.UPDATED):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Circle not found",
                    id=id
                )
        raise ValueError(f"Unexpected response from storage: {resp}")
