"""campus.api.routes.hostedapps

API routes for the HostedApp resource.

Hosted apps are single-file HTML apps published to Campus app hosting
(campus-apphost, classroom#81). Bytes are content-addressed (sha256
bucket keys); the slug is the app's stable address — replacing content
under a slug keeps the address while serving the new version.
"""

import io
from typing import Any

import flask

import campus.flask_campus as flask_campus
import campus.yapper
from campus.common import schema
from campus.common.errors import api_errors

from .. import resources
from ..resources.hostedapps import HostedAppResource

bp = flask.Blueprint('hostedapps', __name__, url_prefix='/hostedapps')

# Lazily initialized yapper - set in init_app() after test fixtures are
# ready. This prevents connection to external services during module
# import in tests.
yapper: campus.yapper.YapperInterface = None  # type: ignore

DEFAULT_CONTENT_TYPE = "text/html"
# Cache content responses briefly; replaced apps keep their slug, so a
# short max-age balances freshness against needless refetches.
CONTENT_CACHE_MAX_AGE = 60


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise hosted app routes with the given Flask app/blueprint."""
    global yapper
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

    The hostedapps blueprint sits behind the api authenticator, so a
    client is always present; the user is None for client-credential
    calls.
    """
    client_id = _principal_id(getattr(flask.g, "current_client", None))
    user_id = _principal_id(getattr(flask.g, "current_user", None))
    if not client_id:
        raise api_errors.UnauthorizedError(
            "App publishing requires an authenticated client"
        )
    return client_id, user_id


def _upload_content_type() -> str:
    """Return the request's Content-Type header, defaulting to text/html."""
    content_type = flask.request.content_type
    if not content_type:
        return DEFAULT_CONTENT_TYPE
    return content_type.split(";")[0].strip() or DEFAULT_CONTENT_TYPE


def _read_body() -> bytes:
    """Read the raw request body (the app's single-file content)."""
    data = flask.request.get_data()
    if not data:
        raise api_errors.InvalidRequestError(
            "App content required: send the raw single-file HTML document "
            "as the request body"
        )
    return data


def _content_response(data: bytes, record: dict) -> flask.Response:
    """Serve app bytes with their stored Content-Type."""
    return flask.send_file(
        io.BytesIO(data),
        mimetype=record["content_type"],
        conditional=True,
        max_age=CONTENT_CACHE_MAX_AGE,
        etag=record["content_hash"],
    )


def _normalise_slug(slug: str) -> str:
    """Normalize a captured by-slug path tail into a slug."""
    return slug.rstrip("/")


@bp.get('/')
@flask_campus.unpack_request
def list_apps(prefix: str | None = None) -> flask_campus.JsonResponse:
    """List hosted apps, optionally under a slug prefix.

    Method:
        GET /hostedapps

    Query Parameters:
        prefix: str | None (optional)
            Only include apps whose slug starts with this prefix.

    Responses:
        200 OK: dict
            {"data": [hosted app resources]}
    """
    result = resources.hostedapps.list(prefix=prefix)
    return {"data": [HostedAppResource.to_resource(r) for r in result]}, 200


@bp.get('/by-slug/<slug>')
def get_app_by_slug(slug: str) -> flask.Response:
    """Get a hosted app's content (or metadata) by slug

    Serve the app's bytes with its stored Content-Type, an ETag and
    short-lived caching headers. Add `meta=1` to receive the metadata
    resource instead.

    Responses:
        200 OK: bytes (application/json metadata with meta=1)
        404 Not Found: {"error": "Hosted app not found"}
    """
    slug = _normalise_slug(slug)
    if flask.request.args.get("meta") in ("1", "true"):
        record = HostedAppResource.get_by_slug(slug)
        return flask.jsonify(HostedAppResource.to_resource(record))
    data, record = HostedAppResource.get_content_by_slug(slug)
    return _content_response(data, record)


@bp.put('/by-slug/<slug>')
def put_app_by_slug(slug: str) -> flask_campus.JsonResponse:
    """Create or replace a hosted app by slug (upsert)

    The request body is the raw app content; the Content-Type header is
    stored and served back. Content is stored content-addressed (sha256
    key), so replacing re-points the slug at the new bytes — consumers
    referencing the slug serve the new version. Replacing keeps the
    slug's URL stable; an optional ?name= sets the display name for new
    apps (replaces keep their stored name unless ?name= is given).

    Responses:
        201 Created: dict (created)
        200 OK: dict (replaced)
        400 Bad Request: invalid slug or empty body
    """
    slug = _normalise_slug(slug)
    data = _read_body()
    client_id, user_id = _principal_ids()
    record, created = HostedAppResource.update_content_by_slug(
        slug,
        data,
        content_type=_upload_content_type(),
        client_id=client_id,
        user_id=user_id,
        name=flask.request.args.get("name"),
    )
    yapper.emit(
        'campus.hostedapps.new' if created else 'campus.hostedapps.update',
        {"hostedapp_id": record["id"], "slug": record["slug"]},
    )
    return (
        HostedAppResource.to_resource(record),
        201 if created else 200,
    )


@bp.delete('/by-slug/<slug>')
def delete_app_by_slug(slug: str) -> flask_campus.JsonResponse:
    """Delete a hosted app (record and content) by slug

    Responses:
        200 OK: {}
        404 Not Found: {"error": "Hosted app not found"}
    """
    slug = _normalise_slug(slug)
    record = HostedAppResource.get_by_slug(slug)
    HostedAppResource.delete_by_slug(slug)
    yapper.emit(
        'campus.hostedapps.delete',
        {"hostedapp_id": record["id"], "slug": slug},
    )
    return {}, 200


@bp.get('/<hostedapp_id>/')
def get_app(hostedapp_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Get a hosted app record by id.

    Responses:
        200 OK: dict
        404 Not Found
    """
    return HostedAppResource(hostedapp_id).get(), 200


@bp.get('/<hostedapp_id>/content/')
def get_app_content(hostedapp_id: schema.CampusID) -> flask.Response:
    """Get a hosted app's content bytes by id.

    Responses:
        200 OK: bytes
        404 Not Found
    """
    resource = HostedAppResource(hostedapp_id)
    record = resource.get()
    data, record = HostedAppResource.get_content_by_slug(record["slug"])
    return _content_response(data, record)

