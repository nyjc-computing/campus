"""campus.api.resources.files

File resource for Campus API.

A file is binary content (blob) stored in the object-storage bucket,
addressed by a stable, human-readable slug
(e.g. ``timetable/specials/breaks``), plus an immutable id for
management access.

Records live in the ``files`` document collection; the bytes live in
the ``files`` bucket, keyed by slug, so replacing content in place
keeps the slug's URL stable.

Note: file records are validated dicts, not campus.model classes. The
record shape is small and campus.api-local; graduating it to a
campus.model.File class can ride the next campus-model release.
"""

import re
import typing

import campus.storage
from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid

files_storage = campus.storage.get_collection("files")

# Bucket for file content. Obtained lazily so that backend selection
# (and its credential resolution) happens on first file operation, not
# at import time.
_bucket: campus.storage.BucketInterface | None = None

BUCKET_NAME = "files"

# Segments with route meaning in /files/... paths; a slug equal to one
# of these would be ambiguous against the id-based content route
# (/files/<file_id>/content/ also matches /files/by-slug/content/).
_RESERVED_SLUGS = frozenset({"content"})

_SLUG_CHARS = re.compile(r"^[A-Za-z0-9._/-]+$")
_MAX_SLUG_LENGTH = 512

_RECORD_FIELDS = (
    "id",
    "slug",
    "name",
    "size",
    "content_type",
    "created_at",
    "updated_at",
    "uploaded_by_client_id",
    "uploaded_by_user_id",
)


def get_files_bucket() -> campus.storage.BucketInterface:
    """Get the file-content bucket for the current environment."""
    global _bucket
    if _bucket is None:
        _bucket = campus.storage.get_bucket(BUCKET_NAME)
    return _bucket


def validate_slug(slug: str) -> str:
    """Validate a file slug and return it unchanged.

    A slug is a slash-separated path-like label. Each segment must be a
    non-empty run of alphanumeric, ``-``, ``_``, ``.`` or ``/`` characters;
    the slug may not begin or end with ``/`` or exceed 512 characters.
    Slugs matching a reserved segment (see _RESERVED_SLUGS) are rejected:
    they would be ambiguous against the id-based content route.

    Args:
        slug: The slug to validate.

    Returns:
        The validated slug.

    Raises:
        api_errors.InvalidRequestError: If the slug is not a valid slug.
    """
    if not slug or len(slug) > _MAX_SLUG_LENGTH:
        raise api_errors.InvalidRequestError(
            f"Invalid file slug: must be 1-{_MAX_SLUG_LENGTH} characters"
        )
    if not _SLUG_CHARS.match(slug):
        raise api_errors.InvalidRequestError(
            "Invalid file slug: only alphanumerics, '-', '_', '.', '/' allowed"
        )
    segments = slug.split("/")
    if any(not segment for segment in segments):
        raise api_errors.InvalidRequestError(
            "Invalid file slug: empty path segments not allowed"
        )
    if any(segment in (".", "..") for segment in segments):
        raise api_errors.InvalidRequestError(
            "Invalid file slug: '.' and '..' segments not allowed"
        )
    if slug in _RESERVED_SLUGS:
        raise api_errors.InvalidRequestError(
            f"Invalid file slug: {slug!r} is a reserved slug"
        )
    return slug


def _get_by_slug(slug: str) -> dict | None:
    """Get the file record for a slug, or None if not found."""
    records = files_storage.get_matching({"slug": slug})
    if not records:
        return None
    return records[0]


class FilesResource:
    """Represents the files resource in Campus API Schema."""

    def __getitem__(self, file_id: schema.CampusID) -> "FileResource":
        """Return a resource object for a specific file.

        Args:
            file_id: The unique identifier of the file.

        Returns:
            FileResource: Resource representing the file.
        """
        return FileResource(file_id)

    def list(self, prefix: str | None = None) -> list[dict]:
        """List file records, optionally under a slug prefix.

        Args:
            prefix: Only include files whose slug starts with this prefix.

        Returns:
            List of file records.
        """
        records = files_storage.get_matching({})
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
        """Create a new file record and upload its content.

        Args:
            slug: The stable slug to address the file by.
            data: The binary content to store.
            content_type: The MIME type of the content.
            client_id: ID of the client performing the upload.
            user_id: ID of the user on whose behalf the upload was made.
            name: Optional display name; defaults to the slug's last segment.

        Returns:
            The created file record.

        Raises:
            api_errors.InvalidRequestError: If the slug is invalid.
            api_errors.ConflictError: If the slug is already taken.
        """
        validate_slug(slug)
        if _get_by_slug(slug) is not None:
            raise api_errors.ConflictError(
                "File slug already taken",
                slug=slug,
            )

        get_files_bucket().put(slug, data, content_type=content_type)
        record = {
            "id": uid.generate_category_uid("file", length=8),
            "slug": slug,
            "name": name if name else slug.rsplit("/", 1)[-1],
            "size": len(data),
            "content_type": content_type,
            "created_at": schema.DateTime.utcnow(),
            "updated_at": schema.DateTime.utcnow(),
            "uploaded_by_client_id": client_id,
            "uploaded_by_user_id": user_id,
        }
        files_storage.insert_one(record)
        return record


class FileResource:
    """Represents a single file."""

    def __init__(self, file_id: schema.CampusID):
        self.file_id = file_id

    def _get_record(self) -> dict:
        """Get the file record by ID.

        Returns:
            The file record.

        Raises:
            api_errors.NotFoundError: If the file does not exist.
        """
        # Document backends return None for a missing id (they do not
        # raise like the table backends do).
        record = files_storage.get_by_id(self.file_id)
        if record is None:
            raise api_errors.NotFoundError(
                "File not found",
                id=self.file_id,
            )
        return record

    @staticmethod
    def get_by_slug(slug: str) -> dict:
        """Get the file record for a slug.

        Args:
            slug: The slug to look up. Invalid slugs yield the same
                not-found outcome as unknown slugs.

        Returns:
            The file record.

        Raises:
            api_errors.NotFoundError: If no file has this slug.
        """
        try:
            validate_slug(slug)
        except api_errors.InvalidRequestError:
            raise api_errors.NotFoundError(
                "File not found",
                slug=slug,
            ) from None
        record = _get_by_slug(slug)
        if record is None:
            raise api_errors.NotFoundError(
                "File not found",
                slug=slug,
            )
        return record

    def get(self) -> dict:
        """Get the file record.

        Raises:
            api_errors.NotFoundError: If the file does not exist.
        """
        return self._get_record()

    def get_content(self) -> tuple[bytes, dict]:
        """Get the file's content bytes and record.

        Returns:
            Tuple of (content bytes, file record).

        Raises:
            api_errors.NotFoundError: If the file does not exist.
        """
        record = self._get_record()
        try:
            data = get_files_bucket().get(record["slug"])
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                "File content not found",
                id=self.file_id,
                slug=record["slug"],
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return data, record

    @staticmethod
    def get_content_by_slug(slug: str) -> tuple[bytes, dict]:
        """Get a file's content bytes and record by slug.

        Args:
            slug: The slug to look up.

        Returns:
            Tuple of (content bytes, file record).

        Raises:
            api_errors.NotFoundError: If no file has this slug.
        """
        record = FileResource.get_by_slug(slug)
        try:
            data = get_files_bucket().get(slug)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                "File content not found",
                slug=slug,
            ) from None
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        return data, record

    def update_content(
        self,
        data: bytes,
        content_type: str,
        client_id: str,
        user_id: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Replace the content of an existing file.

        Args:
            data: The new binary content.
            content_type: The MIME type of the new content.
            client_id: ID of the client performing the upload.
            user_id: ID of the user on whose behalf the upload was made.
            name: Optional new display name.

        Returns:
            The updated file record.

        Raises:
            api_errors.NotFoundError: If the file does not exist.
        """
        record = self._get_record()
        get_files_bucket().put(
            record["slug"], data, content_type=content_type
        )
        updates: dict[str, typing.Any] = {
            "size": len(data),
            "content_type": content_type,
            "updated_at": schema.DateTime.utcnow(),
            "uploaded_by_client_id": client_id,
            "uploaded_by_user_id": user_id,
        }
        if name:
            updates["name"] = name
        files_storage.update_by_id(self.file_id, updates)
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
        """Create or replace a file by slug (upsert).

        The slug's URL stays stable across content replacements, which is
        the point of slug addressing: consumers link the slug, the
        committee replaces the content each term.

        Args:
            slug: The slug to create or replace.
            data: The binary content.
            content_type: The MIME type of the content.
            client_id: ID of the client performing the upload.
            user_id: ID of the user on whose behalf the upload was made.
            name: Optional display name for new files.

        Returns:
            Tuple of (file record, created flag).

        Raises:
            api_errors.InvalidRequestError: If the slug is invalid.
        """
        validate_slug(slug)
        existing = _get_by_slug(slug)
        if existing is not None:
            resource = FileResource(existing["id"])
            record = resource.update_content(
                data, content_type, client_id, user_id, name
            )
            return record, False
        record = FilesResource().new(
            slug, data, content_type, client_id, user_id, name
        )
        return record, True

    def delete(self) -> None:
        """Delete the file record and its content.

        Raises:
            api_errors.NotFoundError: If the file does not exist.
        """
        record = self._get_record()
        try:
            get_files_bucket().delete(record["slug"])
        except campus.storage.errors.NotFoundError:
            pass  # already gone; drop the record regardless
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e
        files_storage.delete_by_id(self.file_id)

    @staticmethod
    def delete_by_slug(slug: str) -> None:
        """Delete a file by slug.

        Args:
            slug: The slug to delete.

        Raises:
            api_errors.NotFoundError: If no file has this slug.
        """
        record = FileResource.get_by_slug(slug)
        FileResource(record["id"]).delete()

    @staticmethod
    def to_resource(record: dict) -> dict:
        """Project a stored record to its API resource shape.

        Args:
            record: The stored file record.

        Returns:
            The record restricted to its resource fields.
        """
        return {field: record[field] for field in _RECORD_FIELDS}
