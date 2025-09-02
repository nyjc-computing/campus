"""campus.storage.documents

This module provides the Documents storage interface.

Documents are used for storing documents that can have different schema.
These documents can be thought of as JSON-like objects, where each document
can have its own structure and fields.
This interface is usually provided by document-oriented databases like MongoDB
or CouchDB.
"""

import os

from .interface import CollectionInterface


def get_db(name: str):
    """Get a collection by name, using appropriate backend for environment."""
    # Check for test mode first
    if os.environ.get("CAMPUS_STORAGE_TEST_MODE"):
        from .backend.memory import MemoryCollection
        return MemoryCollection(name)
    else:
        from .backend.mongodb import MongoDBCollection
        return MongoDBCollection(name)


__all__ = [
    "CollectionInterface",
    "get_db",
]
