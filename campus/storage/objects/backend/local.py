"""campus.storage.objects.backend.local

This module provides the local filesystem backend for the Objects storage interface.

The local backend stores objects as files in a directory structure, mirroring
the key paths. This is intended for development and testing environments.
"""

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from campus.common import devops
from campus.storage import errors
from campus.storage.objects.interface import BucketInterface, ObjectMetadata

# Metadata file suffix
_METADATA_SUFFIX = ".metadata.json"


class LocalBucket(BucketInterface):
    """Local filesystem backend for object storage.

    Stores objects as files in a directory structure. Each object file
    may have a corresponding `.metadata.json` file for storing metadata.

    Example:
        bucket = LocalBucket("uploads", base_path="/tmp/storage")
        bucket.put("avatar.jpg", b"image_data")
        data = bucket.get("avatar.jpg")
    """

    def __init__(self, name: str, base_path: str | None = None):
        """Initialize the local bucket backend.

        Args:
            name: The bucket name (used as subdirectory name)
            base_path: Base directory for storage (default: .storage/{name})
        """
        super().__init__(name)
        if base_path is None:
            base_path = f".storage/{name}"
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """Get the filesystem path for a given key.

        Args:
            key: The object key

        Returns:
            Path object for the object file
        """
        # Prevent directory traversal attacks
        key = key.lstrip("/")
        if ".." in key or key.startswith("~"):
            raise errors.StorageError(
                message="Invalid key: path traversal not allowed",
                group_name=self.name,
                details={"key": key}
            )
        return self.base_path / key

    def _get_metadata_path(self, key: str) -> Path:
        """Get the filesystem path for metadata file.

        Args:
            key: The object key

        Returns:
            Path object for the metadata file
        """
        return self._get_path(key).with_suffix(_METADATA_SUFFIX)

    def _load_metadata(self, key: str) -> dict[str, Any]:
        """Load metadata from disk.

        Args:
            key: The object key

        Returns:
            Dictionary of metadata (may be empty)
        """
        metadata_path = self._get_metadata_path(key)
        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_metadata(self, key: str, metadata: dict[str, Any] | None) -> None:
        """Save metadata to disk.

        Args:
            key: The object key
            metadata: Metadata dictionary to save
        """
        if not metadata:
            return

        metadata_path = self._get_metadata_path(key)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

    def _delete_metadata(self, key: str) -> None:
        """Delete metadata file if it exists.

        Args:
            key: The object key
        """
        metadata_path = self._get_metadata_path(key)
        if metadata_path.exists():
            metadata_path.unlink()

    def put(self, key: str, data: bytes, metadata: dict | None = None) -> None:
        """Upload data to the local filesystem."""
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(path, "wb") as f:
                f.write(data)

            # Save metadata if provided
            if metadata:
                # Add timestamp to metadata
                metadata["_uploaded_at"] = datetime.now().isoformat()
                self._save_metadata(key, metadata)
        except OSError as e:
            raise errors.StorageError(
                message=f"Failed to write object: {e}",
                group_name=self.name,
                details={"key": key}
            ) from e

    def get(self, key: str) -> bytes:
        """Download data from the local filesystem."""
        path = self._get_path(key)

        if not path.exists():
            raise errors.NotFoundError(key, self.name)

        try:
            with open(path, "rb") as f:
                return f.read()
        except OSError as e:
            raise errors.StorageError(
                message=f"Failed to read object: {e}",
                group_name=self.name,
                details={"key": key}
            ) from e

    def delete(self, key: str) -> None:
        """Delete an object from the local filesystem."""
        path = self._get_path(key)

        if not path.exists():
            raise errors.NotFoundError(key, self.name)

        try:
            path.unlink()
            self._delete_metadata(key)
        except OSError as e:
            raise errors.StorageError(
                message=f"Failed to delete object: {e}",
                group_name=self.name,
                details={"key": key}
            ) from e

    def exists(self, key: str) -> bool:
        """Check if an object exists in the local filesystem."""
        path = self._get_path(key)
        return path.exists() and path.is_file()

    def list(self, prefix: str = "", limit: int | None = None) -> list[str]:
        """List object keys with a given prefix."""
        try:
            # Normalize prefix for filesystem matching
            prefix = prefix.lstrip("/")
            prefix_path = self.base_path / prefix if prefix else self.base_path

            if not prefix_path.exists():
                return []

            keys = []
            prefix_len = len(str(self.base_path)) + 1

            # Walk the directory tree
            for root, _, files in os.walk(self.base_path):
                root_path = Path(root)

                for filename in files:
                    # Skip metadata files
                    if filename.endswith(_METADATA_SUFFIX):
                        continue

                    file_path = root_path / filename
                    # Get relative key from base path
                    key = str(file_path)[prefix_len:].replace("\\", "/")

                    # Apply prefix filter
                    if prefix and not key.startswith(prefix):
                        continue

                    keys.append(key)

                    # Apply limit if specified
                    if limit is not None and len(keys) >= limit:
                        return keys

            return keys

        except OSError as e:
            raise errors.StorageError(
                message=f"Failed to list objects: {e}",
                group_name=self.name,
                details={"prefix": prefix}
            ) from e

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL (local: file:// URL).

        Note: For local storage, this returns a file:// URL which
        is only useful for local testing. In production, use Railway
        backend which generates proper HTTP presigned URLs.
        """
        if not self.exists(key):
            raise errors.NotFoundError(key, self.name)

        path = self._get_path(key).resolve()
        return f"file://{path}"

    def get_metadata(self, key: str) -> ObjectMetadata:
        """Get object metadata."""
        path = self._get_path(key)

        if not path.exists():
            raise errors.NotFoundError(key, self.name)

        try:
            stat = path.stat()
            custom_metadata = self._load_metadata(key)

            # Get content type from custom metadata
            content_type = custom_metadata.get("content-type")

            # Create simple ETag from size and mtime
            etag = base64.b64encode(
                f"{stat.st_size}:{stat.st_mtime}".encode()
            ).decode()

            return ObjectMetadata(
                key=key,
                size=stat.st_size,
                last_modified=datetime.fromtimestamp(stat.st_mtime),
                content_type=content_type,
                etag=etag,
                custom=custom_metadata if custom_metadata else None
            )
        except OSError as e:
            raise errors.StorageError(
                message=f"Failed to get metadata: {e}",
                group_name=self.name,
                details={"key": key}
            ) from e

    def copy(self, source_key: str, dest_key: str) -> None:
        """Copy an object within the bucket."""
        source_path = self._get_path(source_key)

        if not source_path.exists():
            raise errors.NotFoundError(source_key, self.name)

        dest_path = self._get_path(dest_key)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            import shutil
            shutil.copy2(source_path, dest_path)

            # Copy metadata if it exists
            source_metadata = self._load_metadata(source_key)
            if source_metadata:
                self._save_metadata(dest_key, source_metadata)
        except OSError as e:
            raise errors.StorageError(
                message=f"Failed to copy object: {e}",
                group_name=self.name,
                details={"source_key": source_key, "dest_key": dest_key}
            ) from e


@devops.block_env(devops.PRODUCTION)
def purge_buckets() -> None:
    """Purge all local bucket storage.

    This function is intended for development/testing environments only.
    It recursively deletes all files in the .storage directory.

    Raises:
        RuntimeError: If purge operation fails
    """
    storage_base = Path(".storage")

    if not storage_base.exists():
        return

    try:
        import shutil
        shutil.rmtree(storage_base)
    except Exception as e:
        raise RuntimeError(f"Failed to purge local bucket storage: {e}") from e
