"""campus.storage.objects.interface

This module provides the Objects storage interface.

Objects (blobs) are stored as key-value pairs where keys are strings
and values are arbitrary bytes. This interface is designed for S3-compatible
object storage systems like Railway Buckets, AWS S3, or local filesystem.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ObjectMetadata:
    """Metadata for a stored object."""

    key: str
    size: int
    last_modified: datetime | None = None
    content_type: str | None = None
    etag: str | None = None
    custom: dict | None = None  # Additional custom metadata


class BucketInterface(ABC):
    """Interface for object/blob storage operations.

    This interface provides S3-compatible object storage operations.
    Implementations can use cloud storage (Railway, AWS S3) or local
    filesystem for testing.
    """

    def __init__(self, name: str):
        """Initialize the bucket interface with a name.

        Args:
            name: The bucket name or prefix for this storage instance.
        """
        self.name = name

    @abstractmethod
    def put(self, key: str, data: bytes, metadata: dict | None = None) -> None:
        """Upload data to the bucket.

        Args:
            key: The object key (path-like string, e.g., "uploads/file.jpg")
            data: The binary data to store
            metadata: Optional custom metadata to attach to the object

        Raises:
            StorageError: If the upload fails
        """
        ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Download data from the bucket.

        Args:
            key: The object key to retrieve

        Returns:
            The binary data stored at the key

        Raises:
            NotFoundError: If the key does not exist
            StorageError: If the download fails
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete an object from the bucket.

        Args:
            key: The object key to delete

        Raises:
            NotFoundError: If the key does not exist
            StorageError: If the deletion fails
        """
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if an object exists in the bucket.

        Args:
            key: The object key to check

        Returns:
            True if the object exists, False otherwise
        """
        ...

    @abstractmethod
    def list(self, prefix: str = "", limit: int | None = None) -> list[str]:
        """List object keys with a given prefix.

        Args:
            prefix: Only return keys starting with this prefix
            limit: Maximum number of keys to return (None for unlimited)

        Returns:
            List of object keys matching the prefix

        Raises:
            StorageError: If the list operation fails
        """
        ...

    @abstractmethod
    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary access.

        This is useful for sharing private objects without proxying
        through a backend service.

        Args:
            key: The object key to generate a URL for
            expires_in: URL expiration time in seconds (default: 3600)

        Returns:
            A presigned URL that grants temporary access to the object

        Raises:
            NotFoundError: If the key does not exist
            StorageError: If URL generation fails
        """
        ...

    @abstractmethod
    def get_metadata(self, key: str) -> ObjectMetadata:
        """Get object metadata without downloading the object.

        Args:
            key: The object key to get metadata for

        Returns:
            ObjectMetadata containing size, timestamps, and custom metadata

        Raises:
            NotFoundError: If the key does not exist
            StorageError: If metadata retrieval fails
        """
        ...

    @abstractmethod
    def copy(self, source_key: str, dest_key: str) -> None:
        """Copy an object within the bucket.

        Args:
            source_key: The source object key
            dest_key: The destination object key

        Raises:
            NotFoundError: If the source key does not exist
            StorageError: If the copy operation fails
        """
        ...
