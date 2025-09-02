"""campus.storage.tables

This module provides the Tables storage interface.

Tables are used for storing rows that follow a common schema.
This interface is usually provided by relational databases like PostgreSQL
or SQLite.
"""

import os
from campus.common import devops

from .interface import TableInterface


def get_db(name: str):
    """Get a table by name, using appropriate backend for environment."""
    # Check for test mode first
    if os.environ.get("CAMPUS_STORAGE_TEST_MODE"):
        from .backend.sqlite import SQLiteTable
        return SQLiteTable(name)
    elif devops.ENV in (devops.STAGING, devops.PRODUCTION):
        from .backend.postgres import PostgreSQLTable
        return PostgreSQLTable(name)
    else:
        # Use SQLite for development when test backends are available
        try:
            from .backend.sqlite import SQLiteTable
            return SQLiteTable(name)
        except ImportError:
            # Fall back to PostgreSQL if SQLite backend is not available
            from .backend.postgres import PostgreSQLTable
            return PostgreSQLTable(name)


__all__ = [
    "TableInterface",
    "get_db",
]
