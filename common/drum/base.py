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
from typing import Any, MutableMapping

from common.schema import Response

GroupName = str
StrId = str
Record = MutableMapping[str, Any]  # Complete set of fields for a record
Update = dict[str, Any]  # Partial set of fields to update
Condition = dict[str, Any]  # Conditions for querying records

PK = "id"


class DrumError(Exception):
    """Base class for all Drum-related errors."""


class DrumResponse(Response):
    """Represents a response from a Drum operation."""


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
    def update_by_id(self, group: GroupName, id: StrId, updates: Update) -> DrumResponse:
        """Update a record in the table by its id"""
        ...

    @abstractmethod
    def update_matching(self, group: str, updates: Update, condition: Condition) -> DrumResponse:
        """Update records in the table that match the condition"""
        ...

    @abstractmethod
    def get_all(self, group: GroupName) -> DrumResponse:
        """Retrieve all records from table"""
        ...

    @abstractmethod
    def get_matching(self, group: GroupName, condition: Condition) -> DrumResponse:
        """Retrieve records from table that match the condition"""
        ...

    @abstractmethod
    def delete_matching(self, group: GroupName, condition: Condition) -> DrumResponse:
        """Delete records from table that match the condition"""
        ...
