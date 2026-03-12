"""campus.storage.objects

This module provides the Objects storage interface.

Objects (blobs) are stored as key-value pairs where keys are strings
and values are arbitrary bytes. This interface is designed for S3-compatible
object storage systems like Railway Buckets, AWS S3, or local filesystem.

Usage Example:
    ```python
    from campus.storage.objects import get_bucket

    # Get a bucket (uses Railway in prod/staging, local in dev/test)
    uploads = get_bucket("uploads")

    # Upload a file
    uploads.put("avatars/user123.jpg", image_data)

    # Generate a presigned URL for sharing
    url = uploads.get_url("avatars/user123.jpg", expires_in=3600)

    # Download a file
    data = uploads.get("avatars/user123.jpg")

    # List files
    keys = uploads.list(prefix="avatars/")

    # Delete a file
    uploads.delete("avatars/user123.jpg")
    ```
"""

import os

__all__ = [
    "BucketInterface",
    "ObjectMetadata",
    "get_bucket",
]

from campus.common import devops

from .interface import BucketInterface, ObjectMetadata


def get_bucket(name: str) -> BucketInterface:
    """Get a bucket by name, using appropriate backend for environment.

    Backend Selection:
        - Test mode (STORAGE_MODE != "0"): Local filesystem backend
        - Production/Staging: Railway Bucket backend
        - Development: Railway if BUCKET env var is set, otherwise Local

    Args:
        name: The bucket name (used as namespace/prefix)

    Returns:
        BucketInterface instance configured for the current environment

    Raises:
        OSError: If Railway backend is selected but required environment
            variables are not set

    Example:
        uploads = get_bucket("uploads")
        uploads.put("file.txt", b"Hello, World!")
    """
    # Import testing module to check for test mode
    from campus.storage.testing import is_test_mode

    if is_test_mode():
        from .backend.local import LocalBucket
        return LocalBucket(name)
    elif devops.ENV in (devops.STAGING, devops.PRODUCTION):
        from .backend.railway import RailwayBucket
        return RailwayBucket(name)
    else:
        # Development: check for Railway environment variables
        # If present, use Railway; otherwise fall back to local
        if "BUCKET" in os.environ and "ENDPOINT" in os.environ:
            from .backend.railway import RailwayBucket
            return RailwayBucket(name)
        from .backend.local import LocalBucket
        return LocalBucket(name)
