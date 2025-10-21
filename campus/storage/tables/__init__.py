"""campus.storage.tables

This module provides the Tables storage interface.

Tables are used for storing rows that follow a common schema.
This interface is usually provided by relational databases like PostgreSQL
or SQLite.
"""

__all__ = [
    "TableInterface",
    "get_db",
]

from campus.common import devops

from .interface import TableInterface


def get_db(name: str):
    """Get a table by name, using appropriate backend for environment."""
    # Import testing module to check for test mode
    from campus.storage.testing import is_test_mode

    if is_test_mode():
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
