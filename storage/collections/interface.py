"""campus.storage.collections.interface

This module provides the Collections storage interface.

Each document in the collection is assumed to have:
1. An `id` primary key (when retrieved; backend implementation
   may not require it).
2. A `created_at` timestamp.
"""

from abc import ABC, abstractmethod

PK = "id"


class CollectionInterface(ABC):
    """Interface for collection storage operations."""

    def __init__(self, name: str):
        """Initialize the collection interface with a name."""
        self.name = name

    @abstractmethod
    def get_by_id(self, doc_id: str) -> dict:
        """Retrieve a document by its ID."""
        ...

    @abstractmethod
    def get_matching(self, query: dict) -> list[dict]:
        """Retrieve documents matching a query."""
        ...

    @abstractmethod
    def insert_one(self, row: dict):
        """Insert a document into the specified table."""
        ...

    @abstractmethod
    def update_by_id(self, doc_id: str, update: dict):
        """Update a document in the specified table."""
        ...

    @abstractmethod
    def update_matching(self, query: dict, update: dict):
        """Update documents matching a query in the specified table."""
        ...

    @abstractmethod
    def delete_by_id(self, doc_id: str):
        """Delete a document from the specified table."""
        ...

    @abstractmethod
    def delete_matching(self, query: dict):
        """Delete documents matching a query in the specified table."""
        ...
