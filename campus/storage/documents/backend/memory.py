"""campus.storage.documents.backend.memory

This module provides an in-memory backend for the Documents storage interface.

This is primarily intended for testing and development scenarios where a
lightweight, in-memory database is sufficient. For production use, prefer
the MongoDB backend.

Implementation:
Uses Python dictionaries to simulate MongoDB collections in memory.
All data is stored in RAM and will be lost when the process exits.
Document IDs are automatically generated if not provided.

Usage Example:
```python
from campus.storage.documents.backend.memory import MemoryCollection

collection = MemoryCollection("users")
collection.insert_one({"id": "123", "name": "John"})
user = collection.get_by_id("123")
collection.update_by_id("123", {"name": "Jane"})
collection.delete_by_id("123")
```
"""

import uuid
from typing import Any, Dict, List, Optional

from campus.storage.documents.interface import CollectionInterface, PK


class MemoryCollection(CollectionInterface):
    """In-memory implementation of the collection storage interface."""

    # Class-level storage to ensure all collections share the same data space
    _storage: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def __init__(self, name: str):
        """Initialize the memory collection interface."""
        super().__init__(name)
        if name not in self._storage:
            self._storage[name] = {}

    def _get_collection(self) -> Dict[str, Dict[str, Any]]:
        """Get the collection storage."""
        return self._storage[self.name]

    def _ensure_id(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure the document has an ID."""
        if PK not in doc:
            doc = doc.copy()
            doc[PK] = str(uuid.uuid4())
        return doc

    def get_by_id(self, doc_id: str) -> Dict[str, Any] | None:
        """Retrieve a document by its ID."""
        collection = self._get_collection()
        return collection.get(doc_id)

    def get_matching(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve documents matching a query."""
        collection = self._get_collection()

        if not query:
            # Return all documents if no query
            return list(collection.values())

        # Simple query handling - exact matches only for this implementation
        matching_docs = []
        for doc in collection.values():
            if self._matches_query(doc, query):
                matching_docs.append(doc)

        return matching_docs

    def _matches_query(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a document matches a query."""
        for key, value in query.items():
            if key not in doc or doc[key] != value:
                return False
        return True

    def insert_one(self, row: Dict[str, Any]):
        """Insert a document into the collection."""
        doc = self._ensure_id(row)
        collection = self._get_collection()
        doc_id = doc[PK]
        collection[doc_id] = doc.copy()

    def update_by_id(self, doc_id: str, update: Dict[str, Any]):
        """Update a document by its ID."""
        collection = self._get_collection()
        if doc_id not in collection:
            return

        # Merge the update (MongoDB-style update)
        doc = collection[doc_id].copy()

        # Handle $unset operations (None values)
        for key, value in update.items():
            if value is None:
                doc.pop(key, None)  # Remove the key if it exists
            else:
                doc[key] = value

        collection[doc_id] = doc

    def update_matching(self, query: Dict[str, Any], update: Dict[str, Any]):
        """Update documents matching a query."""
        matching_docs = self.get_matching(query)
        for doc in matching_docs:
            self.update_by_id(doc[PK], update)

    def delete_by_id(self, doc_id: str):
        """Delete a document by its ID."""
        collection = self._get_collection()
        collection.pop(doc_id, None)

    def delete_matching(self, query: Dict[str, Any]):
        """Delete documents matching a query."""
        matching_docs = self.get_matching(query)
        for doc in matching_docs:
            self.delete_by_id(doc[PK])

    def init_collection(self) -> None:
        """Initialize the collection.

        This method is intended for development/testing environments.
        For memory collections, this is a no-op since collections are
        automatically created when accessed.
        """
        # No-op for memory collections - they're created automatically
        pass

    @classmethod
    def reset_storage(cls):
        """Reset the in-memory storage. Useful for testing."""
        cls._storage.clear()
