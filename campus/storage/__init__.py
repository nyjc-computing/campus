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


def purge_tables() -> None:
    """Purge all tables in the database.

    This is a convenience function that calls the backend-specific purge
    implementation. Intended for development/testing environments only.

    Raises:
        RuntimeError: If purge operation fails
    """
    from .tables.backend.postgres import purge_tables as _purge_tables
    _purge_tables()


def purge_collections() -> None:
    """Purge all collections in the database.

    This is a convenience function that calls the backend-specific purge
    implementation. Intended for development/testing environments only.

    Raises:
        RuntimeError: If purge operation fails
    """
    from .collections.backend.mongodb import purge_collections as _purge_collections
    _purge_collections()


def purge_all() -> None:
    """Purge all tables and collections.

    This is a convenience function that purges both tables and collections.
    Intended for development/testing environments only.

    Raises:
        RuntimeError: If any purge operation fails
    """
    purge_tables()
    purge_collections()


__all__ = [
    "CollectionInterface",
    "TableInterface",
    "StorageError",
    "NotFoundError",
    "NoChangesAppliedError",
    "get_table",
    "get_collection",
    "purge_tables",
    "purge_collections",
    "purge_all",
]
