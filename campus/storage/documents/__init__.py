"""campus.storage.documents

This module provides the Documents storage interface.

Documents are used for storing documents that can have different schema.
These documents can be thought of as JSON-like objects, where each document
can have its own structure and fields.
This interface is usually provided by document-oriented databases like MongoDB
or CouchDB.
"""

__all__ = [
    "CollectionInterface",
    "get_db",
]

from .interface import CollectionInterface


def get_db(name: str):
    """Get a collection by name, using appropriate backend for environment."""
    # Import testing module to check for test mode
    from campus.storage.testing import is_test_mode

    if is_test_mode():
        from .backend.memory import MemoryCollection
        return MemoryCollection(name)
    else:
        from .backend.mongodb import MongoDBCollection
        return MongoDBCollection(name)
