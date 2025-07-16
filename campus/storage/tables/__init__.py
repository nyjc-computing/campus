"""campus.storage.tables

This module provides the Tables storage interface.

Tables are used for storing rows that follow a common schema.
This interface is usually provided by relational databases like PostgreSQL
or SQLite.
"""

from campus.common import devops

from .backend.postgres import PostgreSQLTable

from .interface import TableInterface

def get_db(name: str):
    """Get a table by name, using appropriate backend for environment."""
    if devops.ENV in (devops.STAGING, devops.PRODUCTION):
        return PostgreSQLTable(name)
    else:
        # TODO: Use SQLite for development/testing when backend is implemented
        # For now, use PostgreSQL for all environments
        return PostgreSQLTable(name)


__all__ = [
    "TableInterface",
    "get_db",
]
