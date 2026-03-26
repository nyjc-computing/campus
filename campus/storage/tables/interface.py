"""campus.storage.tables.interface

This module provides the Tables storage interface.

Each row in the table is assumed to have:
1. An `id` primary key.
2. A `created_at` timestamp.
"""

from abc import ABC, abstractmethod

from campus.model import InternalModel, Model

# This constant should match the one in campus.common.schema
PK = "id"


class TableInterface(ABC):
    """Interface for table storage operations."""

    def __init__(self, name: str):
        """Initialize the table interface with a name."""
        self.name = name

    @abstractmethod
    def get_by_id(self, row_id: str) -> dict:
        """Retrieve a row by its ID."""
        ...

    @abstractmethod
    def get_matching(self, query: dict) -> list[dict]:
        """Retrieve rows matching a query."""
        ...

    @abstractmethod
    def insert_one(self, row: dict):
        """Insert a row into the specified table."""
        ...

    def insert_many(
            self,
            rows: list[dict],
            *,
            max_retries: int = 1
    ) -> dict[int, Exception]:
        """Insert multiple rows into the specified table.

        This returns a dict of errors encountered, with row index as key
        and exception as value.
        """
        # Concrete implementations may override this method for improved
        # performance with multiple insertions
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a zero or positive integer")
        # Use a dict as a sparse array for errors to avoid empty indices in list
        errors = {}
        for i, row in enumerate(rows):
            try:
                self.insert_one(row)
            except Exception as e:
                errors[i] = e
        # Happy path
        if not errors:
            return errors
        # Retry while errors remain and max_retries not reached
        retries = 1
        while 0 < retries <= max_retries and errors:
            for i, e in errors.items():
                try:
                    self.insert_one(rows[i])
                except Exception as e:
                    errors[i] = e
                else:
                    del errors[i]
            retries += 1
        return errors

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
