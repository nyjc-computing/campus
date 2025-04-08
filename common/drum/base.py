"""common.drum.base.py

Base classes and common types for the Drum interface.

Common assumptions across storage types:
- attributes/columns/fields are also valid Python identifiers
- primary keys are named `id`
- primary keys are unique strings
- timestamps are stored as RFC3339 strings
- records/documents are grouped by collections/tables
"""

from abc import ABC, abstractmethod
from typing import Any, Literal, NamedTuple

GroupName = str
StrId = str
Record = dict[str, Any]  # Complete set of fields for a record
Update = dict[str, Any]  # Partial set of fields to update

PK = "id"


class DrumResponse(NamedTuple):
    """Represents a response from a Drum operation."""
    status: Literal["ok", "error"]
    message: str
    data: Any | None = None

class DrumInterface(ABC):
    """Abstract base class for Drum implementations."""

    @abstractmethod
    def delete_by_id(self, group: GroupName, id: StrId) -> DrumResponse:
        """Delete a record from table by its id"""
        ...

    @abstractmethod
    def get_by_id(self, group: GroupName, id: StrId) -> DrumResponse:
        """Retrieve a record from table by its id"""
        ...

    @abstractmethod
    def insert(self, group: GroupName, record: Record) -> DrumResponse:
        """Insert a new record into the table"""
        ...

    @abstractmethod
    def set(self, group: GroupName, record: Record) -> DrumResponse:
        """Update an existing record, or insert a new one if it doesn't exist"""
        ...
        
    @abstractmethod
    def update(self, group: GroupName, id: StrId, updates: Update) -> DrumResponse:
        """Update a record in the table by its id"""
        ...
