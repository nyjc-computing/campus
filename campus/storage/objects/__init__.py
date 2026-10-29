"""campus.storage.objects

This module provides the Objects storage interface.

Objects (blobs) are stored as key-value pairs where keys are strings
and values are arbitrary bytes. This interface is designed for S3-compatible
object storage systems like Railway Buckets, AWS S3, or local filesystem.

Usage Example:
    ```python
    from campus.storage.objects import get_bucket

    # Get a bucket (Railway in prod/staging and configured dev, local otherwise)
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

__all__ = [
    "BucketInterface",
    "ObjectMetadata",
    "get_bucket",
]

from campus.common import env

from .interface import BucketInterface, ObjectMetadata


def get_bucket(name: str) -> BucketInterface:
    """Get a bucket by name, using appropriate backend for environment.

    Backend Selection:
        - Test mode (STORAGE_MODE != "0"): Local filesystem backend
        - Production/Staging: Railway Bucket backend
        - Development: Railway if bucket credentials resolve from the
          environment or the deployment vault, otherwise Local

    Args:
        name: The bucket name (used as namespace/prefix)

    Returns:
        BucketInterface instance configured for the current environment

    Raises:
        OSError: If the Railway backend is selected but required
            credentials cannot be resolved

    Example:
        uploads = get_bucket("uploads")
        uploads.put("file.txt", b"Hello, World!")
    """
    # Import testing module to check for test mode
    from campus.storage.testing import is_test_mode

    if is_test_mode():
        from .backend.local import LocalBucket
        return LocalBucket(name)
    elif env.ENV in (env.STAGING, env.PRODUCTION):
        from .backend.railway import RailwayBucket
        return RailwayBucket(name)
    else:
        # Development: use Railway when bucket credentials are configured
        # (environment variables or deployment vault); otherwise local
        from .backend.railway import RailwayBucket, resolve_credentials
        creds = resolve_credentials()
        if creds is not None:
            return RailwayBucket(name, credentials=creds)
        from .backend.local import LocalBucket
        return LocalBucket(name)
