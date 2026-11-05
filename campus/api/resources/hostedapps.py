"""campus.api.resources.hostedapps

HostedApp resource for Campus API.

A HostedApp is a single-file HTML app published to Campus app hosting
(campus-apphost, classroom#81). Records live in the ``hostedapps``
document collection (as ``campus.model.HostedApp`` storage dicts — the
model validates slug, content-hash shape, and status); bytes live in
the ``hostedapps`` bucket, **content-addressed** — keyed by the sha256
of the bytes, not by the slug. The slug is the app's stable
hosting/reference address: replacing an app's content under the same
slug re-points it at the new hash, so consumers referencing the slug
serve the new version.
"""

import hashlib
import re
import typing

import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
from campus.model import HostedApp

hostedapps_storage = campus.storage.get_collection("hostedapps")

# Bucket for app content, CONTENT-ADDRESSED: keys are sha256 hex
# digests, never the slug. Obtained lazily so that backend selection
# (and its credential resolution) happens on first file operation, not
# at import time.
_bucket: campus.storage.BucketInterface | None = None

BUCKET_NAME = "hostedapps"

# HostedApp slugs are single-segment addresses (no slashes): the
# hosting path is one segment under the serving origin, and questions
# reference the slug verbatim.
_SLUG_PATTERN = re.compile(r"^[a-z0-9._-]+$")
_MAX_SLUG_LENGTH = 512


def get_hostedapps_bucket():
    """Get the content-addressed app bucket for the current environment."""
    global _bucket
    if _bucket is None:
        _bucket = campus.storage.get_bucket(BUCKET_NAME)
    return _bucket


def _content_hash(data: bytes) -> str:
    """The sha256 hex digest of the bytes — the bucket key."""
    return hashlib.sha256(data).hexdigest()


def validate_slug(slug: str) -> str:
    """Validate a hosted-app slug and return it unchanged.

    Slugs are single-segment, lowercase addresses: alphanumerics,
    ``-``, ``_`` and ``.``, 1-512 characters.

    Raises:
        api_errors.InvalidRequestError: If the slug is not a valid slug.
    """
    if not slug or len(slug) > _MAX_SLUG_LENGTH:
        raise api_errors.InvalidRequestError(
            f"Invalid hosted app slug: must be 1-{_MAX_SLUG_LENGTH} characters"
        )
    if not _SLUG_PATTERN.fullmatch(slug):
        raise api_errors.InvalidRequestError(
            "Invalid hosted app slug: only lowercase alphanumerics, "
            "'-', '_', '.' allowed"
        )
    return slug


def _get_by_slug(slug: str) -> dict | None:
    """Get the hosted app record for a slug, or None if not found."""
    records = hostedapps_storage.get_matching({"slug": slug})
    if not records:
        return None
    return records[0]


def _blob_reachable_elsewhere(content_hash: str, exclude_id: str) -> bool:
    """Whether another record still references this content hash."""
    return any(
        app["id"] != exclude_id and app.get("content_hash") == content_hash
        for app in hostedapps_storage.get_matching({})
    )


def _delete_blob_if_unreferenced(record: dict) -> None:
    """Delete the content-addressed blob when no record references it.

    Identical content published under two slugs shares one hash; the
    blob must survive until its last referencing record is gone.
    """
    if _blob_reachable_elsewhere(record["content_hash"], record["id"]):
        return
    try:
        get_hostedapps_bucket().delete(record["content_hash"])
    except campus.storage.errors.NotFoundError:
        pass  # already gone; drop the record regardless
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e


class HostedAppsResource:
    """Represents the hostedapps resource in Campus API Schema."""

    def __getitem__(self, hostedapp_id: schema.CampusID) -> "HostedAppResource":
        return HostedAppResource(hostedapp_id)

    def list(self, prefix: str | None = None) -> list[dict]:
        """List hosted app records, optionally under a slug prefix.

        Args:
            prefix: Only include apps whose slug starts with this prefix.

        Returns:
            List of hosted app records, sorted by slug.
        """
        records = hostedapps_storage.get_matching({})
        if prefix:
            records = [
                record for record in records
                if record["slug"].startswith(prefix)
            ]
        return sorted(records, key=lambda record: record["slug"])

    def new(
        self,
        slug: str,
        data: bytes,
        content_type: str,
        client_id: str,
        user_id: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Create a new hosted app record and upload its content.

        Args:
            slug: The stable slug to address the app by.
            data: The single-file app content to store.
            content_type: The MIME type of the content.
            client_id: ID of the client performing the upload.
            user_id: ID of the user on whose behalf the upload was made.
            name: Optional display name; renderers fall back to the slug.

        Returns:
            The created hosted app record.

        Raises:
            api_errors.InvalidRequestError: If the slug is invalid.
            api_errors.ConflictError: If the slug is already taken.
        """
        validate_slug(slug)
        if _get_by_slug(slug) is not None:
            raise api_errors.ConflictError(
                "Hosted app slug already taken",
                slug=slug,
            )
        app = HostedApp(
            slug=slug,
            name=name,
            content_hash=_content_hash(data),
            size=len(data),
            content_type=content_type,
            uploaded_by_client_id=client_id,
            uploaded_by_user_id=user_id,
        )
        get_hostedapps_bucket().put(
            app.content_hash, data, metadata={"content_type": content_type}
        )
        hostedapps_storage.insert_one(app.to_storage())
        return app.to_resource()


class HostedAppResource:
    """Represents a single hosted app."""

    def __init__(self, hostedapp_id: schema.CampusID):
        self.hostedapp_id = hostedapp_id

    def _get_record(self) -> dict:
        """Get the hosted app record by ID.

        Returns:
            The hosted app record.

        Raises:
            api_errors.NotFoundError: If the app does not exist.
        """
        # Document backends return None for a missing id (they do not
        # raise like the table backends do).
        record = hostedapps_storage.get_by_id(self.hostedapp_id)
        if record is None:
            raise api_errors.NotFoundError(
                "Hosted app not found",
                id=self.hostedapp_id,
            )
        return record

    @staticmethod
    def get_by_slug(slug: str) -> dict:
        """Get a hosted app record by slug.

        Invalid slugs yield the same not-found outcome as unknown slugs.

        Raises:
            api_errors.NotFoundError: If no app has this slug.
        """
        try:
            validate_slug(slug)
        except api_errors.InvalidRequestError:
            raise api_errors.NotFoundError(
                "Hosted app not found",
                slug=slug,
            ) from None
        record = _get_by_slug(slug)
        if record is None:
            raise api_errors.NotFoundError(
                "Hosted app not found",
                slug=slug,
            )
        return record

    def get(self) -> dict:
        """Get the hosted app record.

        Raises:
            api_errors.NotFoundError: If the app does not exist.
        """
        return self._get_record()

    @staticmethod
    def get_content_by_slug(slug: str) -> tuple[bytes, dict]:
        """Get a hosted app's content bytes and record by slug.

        The bytes are verified against the record's content_hash — the
        content-addressing doubles as the serve-time integrity check.

        Returns:
            Tuple of (content bytes, hosted app record).

        Raises:
            api_errors.NotFoundError: If no app has this slug, or the
                app has no content yet.
            api_errors.InternalError: If the stored bytes do not match
                the recorded content hash.
        """
        record = HostedAppResource.get_by_slug(slug)
        content_hash = record.get("content_hash")
        if not content_hash:
            raise api_errors.NotFoundError(
                "Hosted app has no content",
                slug=slug,
            )
        try:
            data = get_hostedapps_bucket().get(content_hash)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                "Hosted app content not found",
                slug=slug,
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        if _content_hash(data) != content_hash:
            raise api_errors.InternalError(
                "Hosted app content does not match its recorded hash",
                slug=slug,
            )
        return data, record

    def update_content(
        self,
        data: bytes,
        content_type: str,
        client_id: str,
        user_id: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Replace the content of an existing hosted app.

        Re-pointing is content-addressed: the new bytes get a new hash,
        the record's content_hash moves to it, and the old blob is
        dropped when no other record references it.

        Returns:
            The updated hosted app record.
        """
        record = self._get_record()
        content_hash = _content_hash(data)
        get_hostedapps_bucket().put(
            content_hash, data, metadata={"content_type": content_type}
        )
        updates: dict[str, typing.Any] = {
            "content_hash": content_hash,
            "size": len(data),
            "content_type": content_type,
            "updated_at": schema.DateTime.utcnow(),
            "uploaded_by_client_id": client_id,
            "uploaded_by_user_id": user_id,
        }
        if name:
            updates["name"] = name
        hostedapps_storage.update_by_id(self.hostedapp_id, updates)
        if record["content_hash"] != content_hash:
            _delete_blob_if_unreferenced(record)
        return {**record, **updates}

    @staticmethod
    def update_content_by_slug(
        slug: str,
        data: bytes,
        content_type: str,
        client_id: str,
        user_id: str | None = None,
        name: str | None = None,
    ) -> tuple[dict, bool]:
        """Create or replace a hosted app by slug (upsert).

        The slug's address stays stable across content replacements,
        which is the live-update contract: consumers referencing the
        slug serve the new version.

        Returns:
            Tuple of (hosted app record, created flag).
        """
        validate_slug(slug)
        existing = _get_by_slug(slug)
        if existing is not None:
            resource = HostedAppResource(existing["id"])
            record = resource.update_content(
                data, content_type, client_id, user_id, name
            )
            return record, False
        record = HostedAppsResource().new(
            slug, data, content_type, client_id, user_id, name
        )
        return record, True

    def delete(self) -> None:
        """Delete the hosted app record and its content.

        Raises:
            api_errors.NotFoundError: If the app does not exist.
        """
        record = self._get_record()
        _delete_blob_if_unreferenced(record)
        hostedapps_storage.delete_by_id(self.hostedapp_id)

    @staticmethod
    def delete_by_slug(slug: str) -> None:
        """Delete a hosted app by slug.

        Raises:
            api_errors.NotFoundError: If no app has this slug.
        """
        record = HostedAppResource.get_by_slug(slug)
        HostedAppResource(record["id"]).delete()

    @staticmethod
    def to_resource(record: dict) -> dict:
        """Project a stored record to its API resource shape.

        Projection rides the model's resource-field metadata.
        """
        return HostedApp.from_storage(record).to_resource()
