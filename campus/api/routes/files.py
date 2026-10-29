"""campus.api.routes.files

API routes for the File resource.

Files are binary blobs addressed by a stable slug (consumer-facing,
e.g. ``/api/v1/files/by-slug/timetable/specials/breaks``) or by id
(management). By-slug routes are terminal: the whole path tail after
``by-slug/`` is the slug and content bytes are the default response,
so no slug can collide with a suffix route. Metadata for a slug is
selected with the ``meta`` query parameter, which lives outside path
matching.
"""

import io
from typing import Any

import flask

import campus.yapper
from campus import flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import resources
from ..resources.files import FileResource

bp = flask.Blueprint('files', __name__, url_prefix='/files')

# Lazily initialized yapper - set in init_app() after test fixtures are
# ready. This prevents connection to external services during module
# import in tests.
yapper: campus.yapper.YapperInterface = None  # type: ignore

DEFAULT_CONTENT_TYPE = "application/octet-stream"
# Cache content responses briefly; replaced files keep their slug, so a
# short max-age balances freshness against needless refetches.
CONTENT_CACHE_MAX_AGE = 60


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise file routes with the given Flask app/blueprint."""
    global yapper
    # Initialize yapper after test fixtures have set up the vault
    yapper = campus.yapper.create()
    app.register_blueprint(bp)


def _principal_id(principal: Any) -> str | None:
    """Extract the ID from an authenticated principal.

    The authenticator stores the client/user as a model object (with an
    ``id`` attribute); test doubles may hand back plain dicts.
    """
    if principal is None:
        return None
    value = getattr(principal, "id", None)
    if value is None and isinstance(principal, dict):
        value = principal.get("id")
    return str(value) if value else None


def _principal_ids() -> tuple[str, str | None]:
    """Return the authenticated client and user IDs for this request.

    The files blueprint sits behind the api authenticator, so a client
    is always present; the user is None for client-credential calls.
    """
    client_id = _principal_id(getattr(flask.g, "current_client", None))
    user_id = _principal_id(getattr(flask.g, "current_user", None))
    if not client_id:
        raise api_errors.UnauthorizedError(
            "File uploads require an authenticated client"
        )
    return client_id, user_id


def _upload_content_type() -> str:
    """Return the request's Content-Type header, defaulting to octet-stream."""
    content_type = flask.request.content_type
    if not content_type:
        return DEFAULT_CONTENT_TYPE
    # Strip parameters (e.g. "; charset=...") for storage; the MIME type
    # is what gets served back.
    return content_type.split(";", 1)[0].strip() or DEFAULT_CONTENT_TYPE


def _read_body() -> bytes:
    """Read the raw request body as the file content."""
    data = flask.request.get_data(cache=False)
    if not data:
        raise api_errors.InvalidRequestError(
            "File content required: send the bytes as the request body"
        )
    return data


def _content_response(data: bytes, record: dict) -> flask.Response:
    """Serve file content with its stored type, an ETag and light caching."""
    etag = f'{record["size"]}-{record["updated_at"]}'
    return flask.send_file(
        io.BytesIO(data),
        mimetype=record["content_type"],
        conditional=True,
        max_age=CONTENT_CACHE_MAX_AGE,
        etag=etag,
    )


def _normalise_slug(slug: str) -> str:
    """Normalize a captured by-slug path tail into a slug.

    The path converter can capture a trailing slash; an empty result
    means the URL addressed no slug at all.
    """
    return slug.rstrip("/")


@bp.get('/')
@flask_campus.unpack_request
def list_files(prefix: str | None = None) -> flask_campus.JsonResponse:
    """Summary:
        List file records, optionally under a slug prefix.

    Method:
        GET /files

    Query Parameters:
        prefix: str | None (optional)
            Only include files whose slug starts with this prefix.

    Responses:
        200 OK: dict
            {"data": [file resources]}
    """
    result = resources.file.list(prefix=prefix)
    return {"data": [FileResource.to_resource(r) for r in result]}, 200


@bp.get('/by-slug/<path:slug>', strict_slashes=False)
def get_file_by_slug(slug: str) -> flask.Response:
    """Summary:
        Get a file's content (or metadata with ?meta=1) by slug.

    Method:
        GET /files/by-slug/{slug}

    The whole path tail after /by-slug/ is the slug; the response is the
    file's bytes with its stored Content-Type, an ETag, and short-lived
    caching headers.

    Path Parameters:
        slug: str (required)
            The file's stable slug, e.g. timetable/specials/breaks.

    Query Parameters:
        meta: str | None (optional)
            Return the file metadata resource instead of the content.

    Responses:
        200 OK: bytes
            The file content (application/json metadata with meta=1).

        304 Not Modified
            When the client's If-None-Match matches the ETag.

        404 Not Found: dict
            {"error": "File not found"}
    """
    slug = _normalise_slug(slug)
    if flask.request.args.get("meta") in ("1", "true"):
        record = FileResource.get_by_slug(slug)
        return flask.jsonify(FileResource.to_resource(record))
    data, record = FileResource.get_content_by_slug(slug)
    return _content_response(data, record)


@bp.put('/by-slug/<path:slug>', strict_slashes=False)
def put_file_by_slug(slug: str) -> flask_campus.JsonResponse:
    """Summary:
        Create or replace a file by slug (upsert).

    Method:
        PUT /files/by-slug/{slug}

    The request body is the raw file content; the Content-Type header is
    stored and served back. Replacing keeps the slug's URL stable.

    Path Parameters:
        slug: str (required)
            The stable slug to create or replace.

    Query Parameters:
        name: str | None (optional)
            Display name for new files.

    Body:
        Raw bytes (any Content-Type; defaults to application/octet-stream).

    Responses:
        201 Created: dict
            The created file resource.

        200 OK: dict
            The updated file resource (slug existed).

        400 Bad Request: dict
            Invalid slug or empty body.
    """
    slug = _normalise_slug(slug)
    data = _read_body()
    client_id, user_id = _principal_ids()
    record, created = FileResource.update_content_by_slug(
        slug,
        data,
        content_type=_upload_content_type(),
        client_id=client_id,
        user_id=user_id,
        name=flask.request.args.get("name"),
    )
    yapper.emit(
        'campus.files.new' if created else 'campus.files.update',
        {"file_id": record["id"], "slug": record["slug"]},
    )
    return (
        FileResource.to_resource(record),
        201 if created else 200,
    )


@bp.delete('/by-slug/<path:slug>', strict_slashes=False)
def delete_file_by_slug(slug: str) -> flask_campus.JsonResponse:
    """Summary:
        Delete a file by slug.

    Method:
        DELETE /files/by-slug/{slug}

    Path Parameters:
        slug: str (required)
            The slug to delete.

    Responses:
        200 OK: dict
            Empty object on success.

        404 Not Found: dict
            {"error": "File not found"}
    """
    slug = _normalise_slug(slug)
    record = FileResource.get_by_slug(slug)
    FileResource.delete_by_slug(slug)
    yapper.emit(
        'campus.files.delete', {"file_id": record["id"], "slug": slug}
    )
    return {}, 200


@bp.get('/<file_id>/')
def get_file(file_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Get a file's metadata by ID.

    Method:
        GET /files/{file_id}

    Path Parameters:
        file_id: schema.CampusID (required)
            The unique identifier of the file.

    Responses:
        200 OK: dict
            The file resource.

        404 Not Found: dict
            {"error": "File not found"}
    """
    record = resources.file[file_id].get()
    return FileResource.to_resource(record), 200


@bp.get('/<file_id>/content/')
def get_file_content(file_id: schema.CampusID) -> flask.Response:
    """Summary:
        Get a file's content by ID.

    Method:
        GET /files/{file_id}/content

    Path Parameters:
        file_id: schema.CampusID (required)
            The unique identifier of the file.

    Responses:
        200 OK: bytes
            The file content with its stored Content-Type.

        304 Not Modified
            When the client's If-None-Match matches the ETag.

        404 Not Found: dict
            {"error": "File not found"}
    """
    data, record = resources.file[file_id].get_content()
    return _content_response(data, record)


@bp.put('/<file_id>/content/')
def put_file_content(file_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Replace the content of an existing file by ID.

    Method:
        PUT /files/{file_id}/content

    The request body is the raw file content; the Content-Type header is
    stored and served back. Unlike the by-slug route, this never creates
    a file.

    Path Parameters:
        file_id: schema.CampusID (required)
            The unique identifier of the file.

    Query Parameters:
        name: str | None (optional)
            New display name.

    Body:
        Raw bytes (any Content-Type; defaults to application/octet-stream).

    Responses:
        200 OK: dict
            The updated file resource.

        400 Bad Request: dict
            Empty body.

        404 Not Found: dict
            {"error": "File not found"}
    """
    data = _read_body()
    client_id, user_id = _principal_ids()
    record = resources.file[file_id].update_content(
        data,
        content_type=_upload_content_type(),
        client_id=client_id,
        user_id=user_id,
        name=flask.request.args.get("name"),
    )
    yapper.emit(
        'campus.files.update', {"file_id": file_id, "slug": record["slug"]}
    )
    return FileResource.to_resource(record), 200


@bp.delete('/<file_id>/')
def delete_file(file_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Delete a file by ID.

    Method:
        DELETE /files/{file_id}

    Path Parameters:
        file_id: schema.CampusID (required)
            The unique identifier of the file.

    Responses:
        200 OK: dict
            Empty object on success.

        404 Not Found: dict
            {"error": "File not found"}
    """
    record = resources.file[file_id].get()
    resources.file[file_id].delete()
    yapper.emit(
        'campus.files.delete', {"file_id": file_id, "slug": record["slug"]}
    )
    return {}, 200
