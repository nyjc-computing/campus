"""campus.storage.documents.interface

This module provides the Documents storage interface.

Each document in the collection is assumed to have:
1. An `id` primary key (when retrieved; backend implementation
   may not require it).
2. A `created_at` timestamp.
"""

from abc import ABC, abstractmethod

from campus.model.base import Model

# This constant should match the one in campus.common.schema
PK = "id"


class CollectionInterface(ABC):
    """Interface for collection storage operations."""

    def __init__(self, name: str):
        """Initialize the collection interface with a name."""
        self.name = name

    @abstractmethod
    def get_by_id(self, doc_id: str) -> dict | None:
        """Retrieve a document by its ID."""
        ...

    @abstractmethod
    def get_matching(self, query: dict) -> list[dict]:
        """Retrieve documents matching a query."""
        ...

    @abstractmethod
    def insert_one(self, doc: dict):
        """Insert a document into the specified collection."""
        ...

    def insert_many(self, docs: list[dict]):
        """Insert multiple documents into the specified collection."""
        # Concrete implementations may override this method for improved
        # performance with multiple insertions
        for doc in docs:
            self.insert_one(doc)

    @abstractmethod
    def update_by_id(self, doc_id: str, update: dict):
        """Update a document in the specified collection."""
        ...

    @abstractmethod
    def update_matching(self, query: dict, update: dict):
        """Update documents matching a query in the specified collection."""
        ...

    @abstractmethod
    def delete_by_id(self, doc_id: str):
        """Delete a document from the specified collection."""
        ...

    @abstractmethod
    def delete_matching(self, query: dict):
        """Delete documents matching a query in the specified collection."""
        ...

    @abstractmethod
    def init_from_model(self, name: str, model: type[Model]) -> None:
        """Initialize the collection from a Campus model definition."""
        ...
