"""apps/api/models/source/sourcetype.py
SourceType Models

This module provides classes for creating and managing Campus source types,
which are categories of data sources from third-party platforms and APIs.
"""
from collections.abc import Mapping
from typing import Literal, NotRequired, TypedDict

from apps.common.errors import api_errors
from apps.api.models.base import ModelResponse
from common.devops import Env
from common.drum.jsonfile import get_drum
from common.drum.mongodb import get_db
from common.schema import CampusID, Message, Response

from .integration import IntegrationAuthTypes, Url

SourceTypeID = CampusID

TABLE = "sourcetypes"


class SourceTypeResource(TypedDict, total=False):
    """Database record schema for an integration.

    This is the internal representation of an integration in the database.
    """
    name: str
    description: str
    integration: str
    servers: Mapping[Env, Url]
    api_doc: Url  # URL to OpenAPI spec or API documentation
    security: IntegrationAuthTypes
    scopes: list[str]
    base_url: NotRequired[Url]


class SourceType:
    """SourceType model for handling database operations related to
    source types.
    """

    def __init__(self):
        """Initialize the SourceType model with a storage interface."""
        self.storage = get_drum()

    def disable(self, name: str) -> ModelResponse:
        """Disable a sourcetype."""
        db = get_db()
        db[TABLE].update_one(
            {"@meta": True},
            {"$set": {f"sourcetypes.{name}.enabled": False}}
        )
        return ModelResponse(status="ok", message=Message.SUCCESS)
    
    def enable(self, name: str) -> ModelResponse:
        """Enable a sourcetype."""
        db = get_db()
        db[TABLE].update_one(
            {"@meta": True},
            {"$set": {f"sourcetypes.{name}.enabled": True}}
        )
        return ModelResponse(status="ok", message=Message.SUCCESS)
    
    def get(self, name: str) -> ModelResponse:
        """Get a sourcetype by name from the sourcetypes config."""
        resp = self.storage.get_by_id(TABLE, name)
        # TODO: Cast to appropriate TypedDicts
        match resp:
            case Response(status="error", message=message, data=error):
                raise api_errors.InternalError(message=message, error=error)
            case Response(status="ok", message=Message.FOUND):
                return ModelResponse(*resp)
            case Response(status="ok", message=Message.NOT_FOUND):
                raise api_errors.ConflictError(
                    message="Integration not found",
                    id=name
                )
        raise ValueError(f"Unexpected response from storage: {resp}")
