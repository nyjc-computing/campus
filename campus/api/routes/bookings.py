"""campus.api.routes.bookings

API routes for the Booking resource (campus#1217).

Authority model (ratified 2026-11-23, campus#1217): booking creation
is open to any user principal and pins status "pending" — v1 let
every staff member book, and a booking is a request, not a decision.
Deciding ("approved"/"denied") and any non-owner mutation are gated
on venue authority: venues.admin members act on every venue's
bookings; a venue whose metadata carries a `category` additionally
answers to the standalone `venues.<category-slug>.admin` circle for
that category ("Sports Facilities" → venues.sports-facilities.admin).
There is no flat `bookings.admin` role circle; the bootstrap no
longer seeds one.

Reads stay authentication-only (docs/circles-access-control.md); the
read-tier work is tracked in campus#1216.
"""

import flask

import campus.flask_campus as flask_campus
from campus.common import schema
from campus.common.errors import api_errors

from .. import authz
from ..resources import booking as booking_resource
from ..resources import venue as venue_resource

bp = flask.Blueprint("bookings", __name__, url_prefix="/bookings")


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise booking routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get("/")
@flask_campus.unpack_request
def list_bookings(
    user_id: schema.UserID | None = None,
    venue_id: schema.CampusID | None = None,
    date: schema.Date | None = None,
) -> flask_campus.JsonResponse:
    """List all bookings matching filter requirements.

    Method:
        GET /bookings

    Query Parameters:
        user_id: schema.UserID | None (optional)
            Filter bookings by user ID.
        venue_id: schema.CampusID | None (optional)
            Filter bookings by venue ID.
        date: schema.Date | None (optional)
            Filter bookings by date (YYYY-MM-DD format).

    Responses:
        200 OK: dict
            {"data": [booking resources]}
    """
    bookings = booking_resource.list_bookings(
        user_id=user_id,
        venue_id=venue_id,
        date=date,
    )
    return {"data": [booking_resource.to_resource(b) for b in bookings]}, 200


@bp.post("/")
@flask_campus.unpack_request
def create_booking(
    venue_id: schema.CampusID,
    description: str,
    start_time: str,
    end_time: str,
    date: str,
) -> flask_campus.JsonResponse:
    """Create a new venue booking (pending until decided).

    Method:
        POST /bookings

    Any authenticated user may book; the booking is attributed to the
    principal (client tokens denied — #854). The venue must exist.
    The booking starts "pending": deciding it is the venue
    authority's call (PATCH status).

    The time fields are plain strings rather than schema.Time
    annotations on purpose: flask_campus's request unpacking
    instantiates str-subclass annotations itself and its coercion
    loop does not catch ValueError, so a malformed value would 500
    instead of reaching this handler's 400.

    Body Parameters (application/json):
        venue_id: schema.CampusID (required)
            The ID of the venue to book.
        description: str (required)
            A description of the booking purpose.
        start_time: str (required)
            Start time in HHMM format.
        end_time: str (required)
            End time in HHMM format.
        date: str (required)
            Booking date in YYYY-MM-DD format.

    Responses:
        201 Created: dict
            Booking resource

        400 Bad Request: dict
            {"error": error message} — missing fields, a malformed
            HHMM time or date, or end_time not after start_time.

        403 Forbidden: None
            Returned for client principals (attribution, #854).

        404 Not Found: dict
            {"error": "Venue not found"}

        409 Conflict: dict
            {"error": error message} — an identical booking (same
            venue, date, start and end time) already exists.
    """
    user_id = authz.require_user_principal("create bookings")
    venue_resource.get(venue_id)  # unknown venue → 404
    # Creating your own booking is a self-scope create on venues: staff
    # hold it through the staff → venues:self edge; students (no venues
    # edge) and bare client principals deny. Category never narrows
    # self-scope authority.
    authz.require_resource_access(
        "venues",
        "self",
        "create",
        action_label="create bookings",
    )
    try:
        start = schema.Time(start_time)
        end = schema.Time(end_time)
        booking_date = schema.Date(date)
    except ValueError as e:
        raise api_errors.InvalidRequestError(str(e)) from e
    # HHMM is zero-padded, so lexicographic comparison is time order.
    if end <= start:
        raise api_errors.InvalidRequestError("end_time must be after start_time")
    created = booking_resource.new(
        user_id=schema.UserID(user_id),
        venue_id=venue_id,
        description=description,
        start_time=start,
        end_time=end,
        date=booking_date,
    )
    return booking_resource.to_resource(created), 201


@bp.get("/<booking_id>/")
def get_booking(booking_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Get a single booking by ID.

    Method:
        GET /bookings/{booking_id}

    Path Parameters:
        booking_id: schema.CampusID (required)
            The unique identifier of the booking.

    Responses:
        200 OK: dict
            Booking resource

        404 Not Found: dict
            {"error": "Booking not found"}
    """
    return booking_resource.to_resource(booking_resource.get(booking_id)), 200


@bp.patch("/<booking_id>/")
def update_booking(booking_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Update a booking's description and/or approval status.

    Method:
        PATCH /bookings/{booking_id}

    Authority (campus#1217): a `status` field is a decision on the
    booking — venue authority only (venues.admin globally, or the
    venue category's venues.<category-slug>.admin circle). A
    description-only patch is the owner's right; anyone else needs
    the same venue authority. Venue, date, and times are immutable:
    changes there are delete-and-recreate.

    Path Parameters:
        booking_id: schema.CampusID (required)
            The unique identifier of the booking.

    Body Parameters (application/json):
        description: str (optional)
            New description of the booking purpose.
        status: str (optional)
            "approved" or "denied" (venue authority); "pending"
            resets a decision.

    Responses:
        200 OK: dict
            Booking resource

        400 Bad Request: dict
            {"error": error message} — empty body, unknown fields,
            or a status outside the vocabulary.

        403 Forbidden: None
            A status change (or non-owner description change)
            without venue authority.

        404 Not Found: dict
            {"error": "Booking not found"}
    """
    booking = booking_resource.get(booking_id)
    user_id = authz.require_user_principal("edit bookings")
    payload = flask.request.get_json(silent=True)
    if not isinstance(payload, dict) or not payload:
        raise api_errors.InvalidRequestError(
            'Patch body required: send {"description": str} and/or {"status": "approved" | "denied"}'
        )
    unknown = set(payload) - {"description", "status"}
    if unknown:
        raise api_errors.InvalidRequestError(f"Unknown fields: {sorted(unknown)}")
    if "status" in payload:
        # A status is a decision on the booking: venue authority.
        authz.require_venue_authority(
            booking.venue_id,
            "decide bookings (set status)",
        )
    elif booking.user_id != user_id:
        # Description-only: anyone else is a non-owner edit and needs
        # venue authority.
        authz.require_venue_authority(booking.venue_id, "edit bookings")
    else:
        # The owner's text is a self-scope modify on venues: a staff
        # member manages their own bookings through the
        # staff → venues:self edge.
        authz.require_resource_access(
            "venues",
            "self",
            "modify",
            action_label="edit your booking",
        )
    updated = booking_resource.update(
        booking_id,
        description=payload.get("description", booking_resource.UNSET),
        status=payload.get("status", booking_resource.UNSET),
    )
    return booking_resource.to_resource(updated), 200


@bp.delete("/<booking_id>/")
def delete_booking(booking_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Delete a booking.

    Method:
        DELETE /bookings/{booking_id}

    Authority (campus#1217): the owner may withdraw their own booking
    while it is still pending; once decided (or for anyone other than
    the owner), deletion is venue authority — mirroring v1, where
    users managed their own bookings and the committee managed
    everyone's.

    Path Parameters:
        booking_id: schema.CampusID (required)
            The unique identifier of the booking.

    Responses:
        200 OK: dict
            Empty object on success.

        403 Forbidden: None
            Not the owner (or the booking is decided) and no venue
            authority.

        404 Not Found: dict
            {"error": "Booking not found"}
    """
    booking = booking_resource.get(booking_id)
    user_id = authz.require_user_principal("delete bookings")
    is_owner_withdrawal = booking.user_id == user_id and booking.status == "pending"
    if not is_owner_withdrawal:
        authz.require_venue_authority(booking.venue_id, "delete bookings")
    else:
        # Withdrawing your own pending booking is the delete-own power:
        # the self-scope create bit carries it (c ⇒ delete, ratified
        # convention).
        authz.require_resource_access(
            "venues",
            "self",
            "create",
            action_label="withdraw your booking",
        )
    booking_resource.delete(booking_id)
    return {}, 200
