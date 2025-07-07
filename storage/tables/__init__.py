"""campus.storage.tables

This module provides the Tables storage interface.

Tables are used for storing rows that follow a common schema.
This interface is usually provided by relational databases like PostgreSQL
or SQLite.
"""

from .backend.postgres import PostgreSQLTable

from .interface import TableInterface


def get_db(name: str):
    """Get a table by name."""
    return PostgreSQLTable(name)


__all__ = [
    "TableInterface",
    "get_db",
]
