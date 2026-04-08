"""campus.storage.documents.backend.memory

This module provides an in-memory backend for the Documents storage interface.

This is primarily intended for testing and development scenarios where a
lightweight, in-memory database is sufficient. For production use, prefer
the MongoDB backend.

Implementation:
Uses Python dictionaries to simulate MongoDB collections in memory.
All data is stored in RAM and will be lost when the process exits.
Document IDs are automatically generated if not provided.

Supports MongoDB-style dot notation for nested field updates:
- {"a.b.c": value} sets doc["a"]["b"]["c"] = value
- {"a.b.c": None} removes doc["a"]["b"]["c"]

Usage Example:
```python
from campus.storage.documents.backend.memory import MemoryCollection

collection = MemoryCollection("users")
collection.insert_one({"id": "123", "name": "John"})
user = collection.get_by_id("123")
collection.update_by_id("123", {"name": "Jane"})
collection.update_by_id("123", {"metadata.count": 5})  # Dot notation
collection.delete_by_id("123")
```
"""

import uuid
from typing import Any, Dict, List

from campus.common import devops
from campus.model import Model
from campus.storage.documents.interface import CollectionInterface, PK
from campus.storage.query import gt, gte, is_operator, lt, lte


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
        # Re-create collection if it was cleared by reset_storage()
        if self.name not in self._storage:
            self._storage[self.name] = {}
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

    def get_matching(
        self,
        query: Dict[str, Any],
        *,
        order_by: str | None = None,
        ascending: bool = True,
        limit: int | None = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve documents matching a query.

        Supports exact matches, comparison operators (gt, gte, lt, lte),
        sorting, and pagination.
        """
        collection = self._get_collection()

        if not query:
            # Return all documents if no query
            matching_docs = list(collection.values())
        else:
            # Filter documents based on query
            matching_docs = []
            for doc in collection.values():
                if self._matches_query(doc, query):
                    matching_docs.append(doc)

        # Sort if order_by is specified
        if order_by is not None:
            reverse = not ascending
            matching_docs.sort(key=lambda d: d.get(order_by), reverse=reverse)

        # Apply offset
        if offset > 0:
            matching_docs = matching_docs[offset:]

        # Apply limit
        if limit is not None:
            matching_docs = matching_docs[:limit]

        return matching_docs

    def _matches_query(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a document matches a query.

        Handles exact matches and comparison operators (gt, gte, lt, lte).
        """
        for key, value in query.items():
            if key not in doc:
                return False

            doc_value = doc[key]

            if is_operator(value):
                # Handle comparison operators
                if isinstance(value, gt):
                    if not (doc_value > value.value):
                        return False
                elif isinstance(value, gte):
                    if not (doc_value >= value.value):
                        return False
                elif isinstance(value, lt):
                    if not (doc_value < value.value):
                        return False
                elif isinstance(value, lte):
                    if not (doc_value <= value.value):
                        return False
                else:
                    # Unknown operator, fall back to exact match
                    if doc_value != value.value:
                        return False
            else:
                # Exact match
                if doc_value != value:
                    return False

        return True

    def insert_one(self, row: Dict[str, Any]):
        """Insert a document into the collection."""
        doc = self._ensure_id(row)
        collection = self._get_collection()
        doc_id = doc[PK]
        collection[doc_id] = doc.copy()

    def update_by_id(self, doc_id: str, update: Dict[str, Any]):
        """Update a document by its ID.

        Supports MongoDB-style dot notation for nested field updates:
        - {"a.b.c": 1} sets doc["a"]["b"]["c"] = 1
        - {"a.b.c": None} removes doc["a"]["b"]["c"]
        """
        collection = self._get_collection()
        if doc_id not in collection:
            return

        # Merge the update (MongoDB-style update)
        doc = collection[doc_id].copy()

        # Handle $unset operations (None values) and nested updates
        for key, value in update.items():
            if '.' in key:
                # Handle dot notation for nested fields
                if value is None:
                    self._unset_nested_value(doc, key)
                else:
                    self._set_nested_value(doc, key, value)
            elif value is None:
                doc.pop(key, None)  # Remove the key if it exists
            else:
                doc[key] = value

        collection[doc_id] = doc

    def _set_nested_value(self, doc: Dict[str, Any], key_path: str, value: Any) -> None:
        """Set a nested value in a dictionary using dot notation.

        Args:
            doc: The document to modify
            key_path: Dot-separated path (e.g., "members.abc123" or "a.b.c")
            value: The value to set
        """
        keys = key_path.split('.')
        current = doc

        # Navigate to the parent of the target key, creating nested dicts as needed
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                # If the intermediate value is not a dict, replace it
                current[key] = {}
            current = current[key]

        # Set the final value
        current[keys[-1]] = value

    def _unset_nested_value(self, doc: Dict[str, Any], key_path: str) -> None:
        """Remove a nested value from a dictionary using dot notation.

        Args:
            doc: The document to modify
            key_path: Dot-separated path (e.g., "members.abc123" or "a.b.c")
        """
        keys = key_path.split('.')
        current = doc

        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current or not isinstance(current[key], dict):
                # Path doesn't exist, nothing to unset
                return
            current = current[key]

        # Remove the final key if it exists
        current.pop(keys[-1], None)

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

    def init_from_model(self, name: str, model: type[Model]) -> None:
        """Initialize the table from a Campus model definition."""
        # Document stores do not need any initialization from model
        # definitions as yet.
        # This method is added for future use
        pass

    @classmethod
    def reset_storage(cls):
        """Reset the in-memory storage. Useful for testing."""
        cls._storage.clear()
