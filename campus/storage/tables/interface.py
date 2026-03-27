"""campus.storage.tables.interface

This module provides the Tables storage interface.

Each row in the table is assumed to have:
1. An `id` primary key.
2. A `created_at` timestamp.
"""

from abc import ABC, abstractmethod

from campus.model import InternalModel, Model
from campus.storage import errors as storage_errors

# This constant should match the one in campus.common.schema
PK = "id"


class TableInterface(ABC):
    """Interface for table storage operations."""

    def __init__(self, name: str):
        """Initialize the table interface with a name."""
        self.name = name

    @abstractmethod
    def get_by_id(self, row_id: str) -> dict:
        """Retrieve a row by its ID.

        Args:
            row_id: The ID of the row to retrieve

        Returns:
            The row data as a dictionary

        Raises:
            storage_errors.NotFoundError: If no row exists with the given ID
        """
        ...

    @abstractmethod
    def get_matching(self, query: dict) -> list[dict]:
        """Retrieve rows matching a query."""
        ...

    @abstractmethod
    def insert_one(self, row: dict):
        """Insert a row into the specified table."""
        ...

    @abstractmethod
    def update_by_id(self, row_id: str, update: dict):
        """Update a row in the specified table."""
        ...

    @abstractmethod
    def update_matching(self, query: dict, update: dict):
        """Update rows matching a query in the specified table."""
        ...

    @abstractmethod
    def delete_by_id(self, row_id: str):
        """Delete a row from the specified table."""
        ...

    @abstractmethod
    def delete_matching(self, query: dict):
        """Delete rows matching a query in the specified table."""
        ...

    @abstractmethod
    def init_from_model(self, name: str, model: type[InternalModel | Model]) -> None:
        """Initialize the table from a Campus model definition."""
        ...
