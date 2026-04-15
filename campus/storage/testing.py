"""campus.storage.testing

This module provides test storage backends and configuration for Campus testing.

This allows the storage system to use lightweight, in-memory backends during testing
instead of requiring full database connections.
"""

from typing import Type

from campus.storage.tables.interface import TableInterface
from campus.storage.documents.interface import CollectionInterface


def is_test_mode() -> bool:
    """Check if storage should use test backends based on STORAGE_MODE."""
    from campus.common import env
    storage_mode = env.get("STORAGE_MODE", "0")
    if storage_mode is None:
        return False
    try:
        return int(storage_mode) != 0
    except ValueError:
        return False


def configure_test_storage():
    """Configure storage to use test backends."""
    from campus.common import env
    # Set environment variable to indicate test mode
    env.STORAGE_MODE = "1"  # type: ignore[attr-defined]


def get_table_backend() -> Type[TableInterface]:
    """Get the appropriate table backend based on configuration."""
    if is_test_mode():
        from campus.storage.tables.backend.sqlite import SQLiteTable
        return SQLiteTable
    else:
        from campus.storage.tables.backend.postgres import PostgreSQLTable
        return PostgreSQLTable


def get_collection_backend() -> Type[CollectionInterface]:
    """Get the appropriate collection backend based on configuration."""
    if is_test_mode():
        from campus.storage.documents.backend.memory import MemoryCollection
        return MemoryCollection
    else:
        from campus.storage.documents.backend.mongodb import MongoDBCollection
        return MongoDBCollection


def reset_test_storage():
    """Reset all test storage. Only works in test mode."""
    if is_test_mode():
        from campus.storage.tables.backend.sqlite import SQLiteTable
        from campus.storage.documents.backend.memory import MemoryCollection

        SQLiteTable.reset_database()
        MemoryCollection.reset_storage()
