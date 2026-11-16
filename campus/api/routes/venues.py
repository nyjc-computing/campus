"""campus.api.routes.venues

API routes for the Venue resource: bookable campus venues stored as
documents (campus#1099). The schema is deliberately fluid — freeform
`metadata` + freeform markdown `notes` — so the surface is plain CRUD
over the document, with stable metadata fields to be hoisted into the
model later.

Mutations are gated on the `venues.admin` role circle (user tokens
only); reads require authentication only.
"""

import typing

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz
from ..resources import venue as venue_resource

bp = flask.Blueprint('venues', __name__, url_prefix='/venues')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise venue routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.post('/')
@flask_campus.unpack_request
def create_venue(
        metadata: dict | None = None,
        notes: str | None = None,
) -> flask_campus.JsonResponse:
    """Create a venue.

    Method:
        POST /venues

    Body Parameters (application/json):
        metadata: dict | None (optional)
            Freeform venue facts (name, type, capacity, location, ...).
            Stored verbatim; the shape is deliberately unvalidated
            while the venue schema is fluid.
        notes: str | None (optional)
            Freeform markdown notes.

    Responses:
        201 Created: dict
            The created venue.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `venues.admin` circle (only user tokens are eligible).
    """
    authz.require_resource_admin("venues", "create venues")
    created = venue_resource.new(metadata=metadata, notes=notes)
    return venue_resource.to_resource(created), 201


@bp.get('/')
def list_venues() -> flask_campus.JsonResponse:
    """List all venues, oldest first.

    Method:
        GET /venues

    Responses:
        200 OK: dict
            {"data": [venue resources]}
    """
    venues = venue_resource.list_all()
    return {"data": [venue_resource.to_resource(v) for v in venues]}, 200


@bp.get('/<venue_id>/')
def get_venue(venue_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Get a venue by ID.

    Method:
        GET /venues/{venue_id}

    Path Parameters:
        venue_id: CampusID (required)
            The unique identifier of the venue.

    Responses:
        200 OK: dict
            The venue.

        404 Not Found: dict
            {"error": "Venue not found"}
    """
    venue = venue_resource.get(venue_id)
    return venue_resource.to_resource(venue), 200


@bp.patch('/<venue_id>/')
def patch_venue(venue_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Patch a venue; given fields replace, absent fields stay.

    `metadata` replaces the whole dict (merging partial metadata is
    the caller's job); `{"notes": null}` clears the note.

    Method:
        PATCH /venues/{venue_id}

    Path Parameters:
        venue_id: CampusID (required)
            The unique identifier of the venue.

    Body Parameters (application/json):
        metadata: dict (optional)
            Replacement metadata dict, stored verbatim.
        notes: str | None (optional)
            Replacement markdown notes; null clears.

    Responses:
        200 OK: dict
            The updated venue.

        400 Bad Request: dict
            Empty body, unknown fields, or a non-object `metadata`.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `venues.admin` circle (only user tokens are eligible).

        404 Not Found: dict
            {"error": "Venue not found"}
    """
    authz.require_resource_admin("venues", "edit venues")
    payload = flask.request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        raise api_errors.InvalidRequestError(
            "Patch body required: send {\"metadata\": {...}} and/or "
            "{\"notes\": str | null}"
        )
    unknown = set(payload) - {"metadata", "notes"}
    if unknown:
        raise api_errors.InvalidRequestError(
            f"Unknown fields: {sorted(unknown)}"
        )
    metadata: typing.Any = payload.get("metadata", venue_resource.UNSET)
    if "metadata" in payload and not isinstance(metadata, dict):
        raise api_errors.InvalidRequestError(
            "metadata must be an object"
        )
    notes: typing.Any = payload.get("notes", venue_resource.UNSET)
    updated = venue_resource.update(
        venue_id,
        metadata=metadata,
        notes=notes,
    )
    return venue_resource.to_resource(updated), 200


@bp.delete('/<venue_id>/')
def delete_venue(venue_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Delete a venue.

    Method:
        DELETE /venues/{venue_id}

    Path Parameters:
        venue_id: CampusID (required)
            The unique identifier of the venue.

    Responses:
        200 OK: dict
            Empty object on success.

        403 Forbidden: None
            Returned if the caller is not a member of the
            `venues.admin` circle (only user tokens are eligible).

        404 Not Found: dict
            {"error": "Venue not found"}
    """
    authz.require_resource_admin("venues", "delete venues")
    venue_resource.delete(venue_id)
    return {}, 200
