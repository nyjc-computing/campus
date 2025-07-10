"""campus.storage

This module provides the common storage interface for the campus application.

Two kinds of storage interface are provided:
1. Tables: For storing rows following a common schema.
2. Collections: For storing documents that can have different schemas.
"""

from . import collections, tables

from .collections import CollectionInterface
from .tables import TableInterface
from .errors import StorageError, NotFoundError, NoChangesAppliedError


def get_table(name: str):
    """Get a table by name."""
    return tables.get_db(name)

def get_collection(name: str):
    """Get a collection by name."""
    return collections.get_db(name)


__all__ = [
    "CollectionInterface",
    "TableInterface",
    "StorageError",
    "NotFoundError", 
    "NoChangesAppliedError",
    "get_table",
    "get_collection",
]
