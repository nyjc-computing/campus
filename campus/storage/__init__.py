"""campus.storage

This module provides the common storage interface for the campus application.

Three kinds of storage interface are provided:
1. Tables: For storing rows following a common schema.
2. Documents: For storing documents that can have different schemas.
3. Objects: For storing binary blobs with S3-compatible object storage.
"""

__all__ = [
    "BucketInterface",
    "CollectionInterface",
    "ConflictError",
    "NoChangesAppliedError",
    "NotFoundError",
    "ObjectMetadata",
    "TableInterface",
    "StorageError",
    "get_bucket",
    "get_collection",
    "get_table",
    "purge_all",
    "purge_buckets",
    "purge_collections",
    "purge_tables",
    # Query operators
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "is_operator",
]

from campus.common import devops

from . import documents, objects, tables

from .documents import CollectionInterface
from .tables import TableInterface
from .objects import BucketInterface, ObjectMetadata
from .errors import (
    StorageError,
    ConflictError,
    NotFoundError,
    NoChangesAppliedError
)
from .query import gt, gte, lt, lte, between, is_operator


def get_table(name: str) -> TableInterface:
    """Get a table by name."""
    return tables.get_db(name)


def get_collection(name: str):
    """Get a collection by name."""
    return documents.get_db(name)


def get_bucket(name: str):
    """Get a bucket by name."""
    return objects.get_bucket(name)


@devops.block_env(devops.PRODUCTION)
@devops.confirm_action_in_env(devops.STAGING)
def purge_tables() -> None:
    """Purge all tables in the database.

    This is a convenience function that calls the backend-specific purge
    implementation. Intended for development/testing environments only.

    Raises:
        RuntimeError: If purge operation fails
    """
    from .tables.backend.postgres import purge_tables as _purge_tables
    _purge_tables()


@devops.block_env(devops.PRODUCTION)
@devops.confirm_action_in_env(devops.STAGING)
def purge_collections() -> None:
    """Purge all collections in the database.

    This is a convenience function that calls the backend-specific purge
    implementation. Intended for development/testing environments only.

    Raises:
        RuntimeError: If purge operation fails
    """
    from .documents.backend.mongodb import purge_collections as _purge_collections
    _purge_collections()


@devops.block_env(devops.PRODUCTION)
@devops.confirm_action_in_env(devops.STAGING)
def purge_all() -> None:
    """Purge all tables, collections, and buckets.

    This is a convenience function that purges tables, collections, and buckets.
    Intended for development/testing environments only.

    Raises:
        RuntimeError: If any purge operation fails
    """
    purge_tables()
    purge_collections()
    purge_buckets()


@devops.block_env(devops.PRODUCTION)
@devops.confirm_action_in_env(devops.STAGING)
def purge_buckets() -> None:
    """Purge all objects in buckets.

    This is a convenience function that calls the backend-specific purge
    implementation. Intended for development/testing environments only.

    Raises:
        RuntimeError: If purge operation fails
    """
    from .objects.backend.local import purge_buckets as _purge_buckets
    _purge_buckets()
