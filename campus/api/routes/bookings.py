"""campus.api.routes.booking

API routes for the Booking resource.
"""

import flask

from campus import flask_campus
from campus.common import schema

from .. import resources

import campus.storage
import campus.model

bp = flask.Blueprint('bookings', __name__, url_prefix='/bookings')


def init_app(app: flask.Flask | flask.Blueprint) -> None:
    """Initialise booking routes with the given Flask app/blueprint."""
    app.register_blueprint(bp)


@bp.get('/')
@flask_campus.unpack_request
def list_bookings(
    user_id: schema.UserID | None = None,
    venue_id: schema.CampusID | None = None,
    date: schema.Date | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        List all bookings matching filter requirements.

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
    return {"error": "Not implemented"}, 501


@bp.post('/')
@flask_campus.unpack_request
def create_booking(
    venue_id: schema.CampusID,
    description: str,
    start_time: schema.Time,
    end_time: schema.Time,
    date: schema.Date,
) -> flask_campus.JsonResponse:
    """Summary:
        Create a new venue booking.

    Method:
        POST /bookings

    Body Parameters (application/json):
        venue_id: schema.CampusID (required)
            The ID of the venue to book.
        description: str (required)
            A description of the booking purpose.
        start_time: schema.Time (required)
            Start time in HH:MM format.
        end_time: schema.Time (required)
            End time in HH:MM format.
        date: schema.Date (required)
            Booking date in YYYY-MM-DD format.

    Responses:
        201 Created: dict
            Booking resource

        400 Bad Request: dict
            {"error": error message}
    """
    return {"error": "Not implemented"}, 501


@bp.get('/<booking_id>/')
def get_booking(booking_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Get a single booking by ID.

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
    return {"error": "Not implemented"}, 501


@bp.patch('/<booking_id>/')
@flask_campus.unpack_request
def update_booking(
    *,
    booking_id: schema.CampusID,
    description: str | None = None,
) -> flask_campus.JsonResponse:
    """Summary:
        Update an existing booking.

    Note: Only the description can be modified. Changes to venue, date,
        or time require creating a new booking.

    Method:
        PATCH /bookings/{booking_id}

    Path Parameters:
        booking_id: schema.CampusID (required)
            The unique identifier of the booking.

    Body Parameters (application/json):
        description: str (optional)
            New description for the booking.

    Responses:
        200 OK: dict
            Empty object on success.

        400 Bad Request: dict
            {"error": error message}

        404 Not Found: dict
            {"error": "Booking not found"}
    """
    return {"error": "Not implemented"}, 501


@bp.delete('/<booking_id>/')
def delete_booking(booking_id: schema.CampusID) -> flask_campus.JsonResponse:
    """Summary:
        Delete a booking.

    Method:
        DELETE /bookings/{booking_id}

    Path Parameters:
        booking_id: schema.CampusID (required)
            The unique identifier of the booking.

    Responses:
        200 OK: dict
            Empty object on success.

        404 Not Found: dict
            {"error": "Booking not found"}
    """
    return {"error": "Not implemented"}, 501
