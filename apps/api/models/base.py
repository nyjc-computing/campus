"""apps/palmtree/models/base.py

Base types and classes for all Palmtree models.
"""

from typing import Any, TypedDict

from common.schema import Message, Response
from common.utils import utc_time


class ModelResponse(Response):
    """Represents a response from any model operation."""


class BaseRecord(TypedDict):
    """Base class for all records in the Palmtree system.

    Records are Mapping objects that represent a single record in the database.
    BaseRecord reflects the keys that are common to all records in the system.
    """
    id: str
    created_at: utc_time.datetime