"""campus.storage.collections

This module provides the Collections storage interface.

Collections are used for storing documents that can have different schema.
These documents can be thought of as JSON-like objects, where each document
can have its own structure and fields.
This interface is usually provided by document-oriented databases like MongoDB
or CouchDB.
"""

import backend.mongodb

from .interface import CollectionInterface


def get_db(name: str):
    """Get a collection by name."""
    return backend.mongodb.MongoDBCollection(name)


__all__ = [
    "CollectionInterface",
    "get_db",
]
