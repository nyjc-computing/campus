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
    def get_matching(
        self,
        query: dict,
        *,
        order_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
        offset: int = 0
    ) -> list[dict]:
        """Retrieve documents matching a query.

        Args:
            query: Dictionary of field to value mappings for filtering.
                   Values can be exact matches or Operator instances for
                   comparison queries (gt, gte, lt, lte).
                   Multiple fields are treated as implicit AND (all conditions must match).
            order_by: Field name to sort by. If None, results are unordered.
            ascending: Sort direction. True for ascending, False for descending.
            limit: Maximum number of documents to return. If None, all matching documents are returned.
            offset: Number of documents to skip before returning results.

        Returns:
            List of matching documents as dictionaries.

        Example:
            # Simple exact match
            get_matching({"user_id": "user_123"})

            # With operators
            get_matching({"duration_ms": gt(1000)})

            # Multiple fields (implicit AND)
            get_matching({"user_id": "user_123", "status": "active"})

            # With sorting and pagination
            get_matching({"status": "active"}, order_by="created_at", ascending=False, limit=10, offset=0)
        """
        ...

    @abstractmethod
    def insert_one(self, doc: dict):
        """Insert a document into the specified collection."""
        ...

    def insert_many(
            self,
            docs: list[dict],
            *,
            max_retries: int = 1
    ) -> dict[int, Exception]:
        """Insert multiple documents into the specified collection."""
        # Concrete implementations may override this method for improved
        # performance with multiple insertions
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a zero or positive integer")
        # Use a dict as a sparse array for errors to avoid empty indices in list
        errors = {}
        for i, row in enumerate(docs):
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
                    self.insert_one(docs[i])
                except Exception as e:
                    errors[i] = e
                else:
                    del errors[i]
            retries += 1
        return errors

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
