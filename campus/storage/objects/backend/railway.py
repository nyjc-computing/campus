"""campus.storage.objects.backend.railway

This module provides the Railway Bucket backend for the Objects storage interface.

Railway Buckets are S3-compatible object storage. This backend uses boto3
to interact with Railway's S3-compatible API.

Credentials Required:
    BUCKET: The globally unique bucket name (e.g., "my-bucket-jdhhd8oe18xi")
    SECRET_ACCESS_KEY: The S3 secret key
    ACCESS_KEY_ID: The S3 key ID
    REGION: The S3 region (typically "auto"; optional, defaults to "auto")
    ENDPOINT: The S3 endpoint URL (e.g., the bucket's private Railway URL)

Credentials are resolved from environment variables first, then from the
deployment vault via env.getsecret (same source as SECRET_KEY). Storing
them in the vault keeps them out of the service variable list; the private
ENDPOINT URL is only reachable from within the Railway environment.

Railway Documentation: https://docs.railway.com/storage-buckets.md
"""

import logging
import os
from collections.abc import Mapping
from typing import Any

import boto3
from botocore.config import Config

from campus.storage import errors
from campus.storage.objects.interface import BucketInterface, ObjectMetadata

logger = logging.getLogger(__name__)

# Required credential keys; resolution failure is a configuration error
CREDENTIAL_VARS = ("BUCKET", "ENDPOINT", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY")
# Optional credential keys with fallbacks
OPTIONAL_VARS = ("REGION",)


def resolve_credential(name: str) -> str | None:
    """Resolve a bucket credential from environment or deployment vault.

    Environment variables take precedence (deployment-level overrides);
    missing names fall back to the deployment vault via env.getsecret,
    the same source that serves SECRET_KEY. Lookup failures (secret not
    configured, vault unreachable) resolve to None so bucket factory
    selection can fall back to another backend.

    Args:
        name: Credential key (e.g., "BUCKET", "SECRET_ACCESS_KEY")

    Returns:
        The credential value, or None if unavailable from both sources
    """
    if name in os.environ:
        return os.environ[name]
    from campus.common import env
    try:
        return env.getsecret(name)
    except Exception:
        logger.debug("No %s credential from environment or vault", name)
        return None


def resolve_credentials() -> dict[str, str | None] | None:
    """Resolve all Railway bucket credentials, or None if unconfigured.

    Returns None when BUCKET or ENDPOINT is unavailable, meaning the
    bucket is not configured for this deployment. A partial configuration
    (BUCKET and ENDPOINT present but keys missing) returns what resolved
    so that RailwayBucket construction raises the loud missing-variable
    error instead of silently falling back to another backend.

    Returns:
        Dict of resolved credentials, or None if the bucket is unconfigured
    """
    creds: dict[str, str | None] = {
        var: resolve_credential(var)
        for var in CREDENTIAL_VARS + OPTIONAL_VARS
    }
    if not creds["BUCKET"] or not creds["ENDPOINT"]:
        return None
    return creds


class RailwayBucket(BucketInterface):
    """Railway Storage Bucket backend using S3-compatible API.

    Railway Buckets provide private, S3-compatible object storage with
    free unlimited API operations and egress.

    Example:
        bucket = RailwayBucket("uploads")
        bucket.put("avatar.jpg", image_data)
        url = bucket.get_url("avatar.jpg", expires_in=3600)
    """

    def __init__(self, name: str, credentials: Mapping[str, str | None] | None = None):
        """Initialize the Railway bucket backend.

        Args:
            name: The bucket name prefix (used as a namespace within the bucket)
            credentials: Explicit credential overrides (e.g., for testing).
                When omitted, credentials are resolved from environment
                variables first, then the deployment vault via env.getsecret.

        Raises:
            OSError: If required credentials cannot be resolved
        """
        super().__init__(name)

        creds = credentials if credentials is not None else {
            var_name: resolve_credential(var_name)
            for var_name in CREDENTIAL_VARS + OPTIONAL_VARS
        }

        self._bucket_name = creds.get("BUCKET")
        self._endpoint = creds.get("ENDPOINT")
        self._access_key = creds.get("ACCESS_KEY_ID")
        self._secret_key = creds.get("SECRET_ACCESS_KEY")
        self._region = creds.get("REGION") or "auto"

        # Validate required credentials
        missing = [
            var_name for var_name in CREDENTIAL_VARS
            if not creds.get(var_name)
        ]

        if missing:
            raise OSError(
                f"Missing required Railway environment variables: "
                f"{', '.join(missing)}"
            )

        self._s3_client = None  # Lazy initialization

    def _get_client(self):
        """Get or create boto3 S3 client configured for Railway.

        The client is lazily initialized to avoid overhead if the bucket
        is never used.

        Returns:
            boto3 S3 client configured for Railway endpoint
        """
        if self._s3_client is None:
            # Configure botocore for Railway
            config = Config(
                region_name=self._region,
                retries={"max_attempts": 3, "mode": "adaptive"},
            )

            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self._endpoint,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                config=config,
            )
        return self._s3_client

    def _full_key(self, key: str) -> str:
        """Get the full key with bucket name prefix.

        Args:
            key: The object key

        Returns:
            Full key path with bucket name as prefix
        """
        # Normalize key: remove leading slash, ensure no double slashes
        key = key.lstrip("/")
        if self.name:
            return f"{self.name}/{key}" if key else self.name
        return key

    def _map_boto_error(self, error, key: str, context: str) -> errors.StorageError:
        """Map boto3 exceptions to Campus storage errors.

        Args:
            error: The boto3/botocore exception
            key: The object key involved
            context: Description of the operation being performed

        Returns:
            Appropriate Campus storage error
        """
        error_code = getattr(error, "response", {}).get("Error", {}).get("Code", "")

        if error_code in ("NoSuchKey", "404"):
            return errors.NotFoundError(key, self.name)
        elif error_code in ("EntityAlreadyExists", "BucketAlreadyExists"):
            return errors.ConflictError(
                message="Object already exists",
                group_name=self.name,
                details={"key": key}
            )
        else:
            return errors.StorageError(
                message=f"{context} failed: {error_code}",
                group_name=self.name,
                details={"key": key, "error": str(error)}
            )

    def put(self, key: str, data: bytes, metadata: dict | None = None) -> None:
        """Upload data to Railway bucket."""
        client = self._get_client()
        full_key = self._full_key(key)

        try:
            put_args: dict[str, Any] = {
                "Bucket": self._bucket_name,
                "Key": full_key,
                "Body": data,
            }

            # Add metadata if provided (convert to S3 format)
            if metadata:
                # S3 uses lowercase keys for custom metadata
                custom_metadata = {f"x-amz-meta-{k}": v for k, v in metadata.items()}
                put_args["Metadata"] = custom_metadata

            client.put_object(**put_args)

        except Exception as e:
            raise self._map_boto_error(e, key, "Upload") from e

    def get(self, key: str) -> bytes:
        """Download data from Railway bucket."""
        client = self._get_client()
        full_key = self._full_key(key)

        try:
            response = client.get_object(
                Bucket=self._bucket_name,
                Key=full_key
            )
            return response["Body"].read()

        except Exception as e:
            raise self._map_boto_error(e, key, "Download") from e

    def delete(self, key: str) -> None:
        """Delete an object from Railway bucket."""
        client = self._get_client()
        full_key = self._full_key(key)

        try:
            client.delete_object(
                Bucket=self._bucket_name,
                Key=full_key
            )

        except Exception as e:
            raise self._map_boto_error(e, key, "Delete") from e

    def exists(self, key: str) -> bool:
        """Check if an object exists in Railway bucket."""
        client = self._get_client()
        full_key = self._full_key(key)

        try:
            client.head_object(
                Bucket=self._bucket_name,
                Key=full_key
            )
            return True

        except Exception as e:
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if error_code in ("NoSuchKey", "404"):
                return False
            raise self._map_boto_error(e, key, "Exists check") from e

    def list(self, prefix: str = "", limit: int | None = None) -> list[str]:
        """List object keys with a given prefix."""
        client = self._get_client()
        full_prefix = self._full_key(prefix)

        try:
            list_args: dict[str, Any] = {
                "Bucket": self._bucket_name,
                "Prefix": full_prefix,
            }

            keys = []
            continuation_token = None

            while True:
                if continuation_token:
                    list_args["ContinuationToken"] = continuation_token

                response = client.list_objects_v2(**list_args)

                # Extract keys from response
                for obj in response.get("Contents", []):
                    # Strip the bucket name prefix to return relative keys
                    obj_key = obj["Key"]
                    if self.name and obj_key.startswith(f"{self.name}/"):
                        obj_key = obj_key[len(f"{self.name}/"):]
                    keys.append(obj_key)

                    # Check limit
                    if limit is not None and len(keys) >= limit:
                        return keys[:limit]

                # Check if there are more results
                if not response.get("IsTruncated"):
                    break

                continuation_token = response.get("NextContinuationToken")

            return keys

        except Exception as e:
            # Empty bucket is not an error - just return empty list
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            if error_code in ("NoSuchBucket", "404"):
                return []
            raise errors.StorageError(
                message=f"List operation failed: {error_code}",
                group_name=self.name,
                details={"prefix": prefix, "error": str(e)}
            ) from e

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for temporary access."""
        client = self._get_client()
        full_key = self._full_key(key)

        try:
            url = client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket_name,
                    "Key": full_key
                },
                ExpiresIn=expires_in
            )
            return url

        except Exception as e:
            raise self._map_boto_error(e, key, "URL generation") from e

    def get_metadata(self, key: str) -> ObjectMetadata:
        """Get object metadata from Railway bucket."""
        client = self._get_client()
        full_key = self._full_key(key)

        try:
            response = client.head_object(
                Bucket=self._bucket_name,
                Key=full_key
            )

            # Extract custom metadata (S3 prefixes with x-amz-meta-)
            custom_metadata = {}
            for meta_key, meta_value in response.get("Metadata", {}).items():
                # Strip the x-amz-meta- prefix if present
                clean_key = meta_key.replace("x-amz-meta-", "")
                custom_metadata[clean_key] = meta_value

            # Parse last modified
            last_modified = response.get("LastModified")

            return ObjectMetadata(
                key=key,
                size=response.get("ContentLength", 0),
                last_modified=last_modified,
                content_type=response.get("ContentType"),
                etag=response.get("ETag", "").strip('"'),
                custom=custom_metadata if custom_metadata else None
            )

        except Exception as e:
            raise self._map_boto_error(e, key, "Metadata retrieval") from e

    def copy(self, source_key: str, dest_key: str) -> None:
        """Copy an object within the Railway bucket."""
        client = self._get_client()
        full_source = self._full_key(source_key)
        full_dest = self._full_key(dest_key)

        try:
            client.copy_object(
                Bucket=self._bucket_name,
                CopySource={"Bucket": self._bucket_name, "Key": full_source},
                Key=full_dest
            )

        except Exception as e:
            raise self._map_boto_error(e, source_key, "Copy") from e
