"""campus.api.resources.booking

Booking resource for Campus API: venue bookings in the fixed table
shape of campus.model.VenueBooking (campus#1217). Unlike the
documents-backed venues, bookings carry user attribution and an
approval status, so they live in a storage table (`init_storage`,
wired by the api bootstrap and migrations/013) rather than a
self-creating collection.

Boundary (as with venues): the resource stays ungated for in-process
callers; the routes decide authority. Creation is open to any user
principal and pins status "pending" — v1 let every staff member book;
decisions ("approved"/"denied") and non-owner edits are gated on
venue authority (authz.require_venue_authority: venues.admin
globally, venues.<category-slug>.admin for the venue's category).
"""

import typing

import campus.model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors

# Sentinel for "field not given" in update calls, mirroring venues:
# absence and an explicit value must stay distinguishable.
UNSET = object()

venue_booking_table = campus.storage.get_table("venue_bookings")

# The approval vocabulary for VenueBooking.status (campus-model
# 0.2.6): creation pins "pending"; the booking authority moves a
# booking to one of the two decided states. Enforced at the route
# layer; the model field is a plain string.
BOOKING_STATUSES = ("pending", "approved", "denied")


def to_resource(booking: campus.model.VenueBooking) -> dict:
    """Project a booking into its API resource form."""
    return booking.to_resource()


def init_storage() -> None:
    """Initialize storage."""
    venue_booking_table.init_from_model(
        "venue_bookings",
        campus.model.VenueBooking,
    )


def get(booking_id: schema.CampusID) -> campus.model.VenueBooking:
    """Get a booking by ID.

    Raises:
        api_errors.NotFoundError: If the booking does not exist.
    """
    try:
        record = venue_booking_table.get_by_id(str(booking_id))
    except campus.storage.errors.NotFoundError:
        record = None
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    if record is None:
        raise api_errors.NotFoundError(
            f"Booking not found: {booking_id}",
            id=str(booking_id),
        )
    return campus.model.VenueBooking.from_storage(record)


def list_bookings(
    user_id: schema.UserID | None = None,
    venue_id: schema.CampusID | None = None,
    date: schema.Date | None = None,
) -> list[campus.model.VenueBooking]:
    """Bookings matching the given filters, earliest date first.

    Booking counts stay small (v1 pruned its bookings table on a
    14-day cycle), so there is no pagination; callers filter
    client-side beyond the three query parameters.
    """
    query: dict[str, typing.Any] = {}
    if user_id is not None:
        query["user_id"] = str(user_id)
    if venue_id is not None:
        query["venue_id"] = str(venue_id)
    if date is not None:
        query["date"] = str(date)
    try:
        records = venue_booking_table.get_matching(
            query,
            order_by="date",
            ascending=True,
        )
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return [campus.model.VenueBooking.from_storage(r) for r in records]


def new(
    user_id: schema.UserID,
    venue_id: schema.CampusID,
    description: str,
    start_time: schema.Time,
    end_time: schema.Time,
    date: schema.Date,
) -> campus.model.VenueBooking:
    """Create a pending booking attributed to the given user.

    The venue is not re-checked here: the route resolves it first
    (404 semantics) and creation needs no venue authority — a booking
    is a request, not a decision (campus#1217).

    Raises:
        api_errors.ConflictError: If an identical booking (same
            venue, date, start and end time) already exists. The
            check is read-then-write: the model's __constraints__
            declaration is not emitted as DDL by the storage
            generators (same as every campus model), so the guard is
            app-layer and best-effort under concurrency.
    """
    booking = campus.model.VenueBooking(
        user_id=schema.UserID(user_id),
        venue_id=schema.CampusID(venue_id),
        description=schema.String(description),
        start_time=schema.Time(start_time),
        end_time=schema.Time(end_time),
        date=schema.Date(date),
    )
    duplicates = venue_booking_table.get_matching(
        {
            "venue_id": str(booking.venue_id),
            "date": str(booking.date),
            "start_time": str(booking.start_time),
            "end_time": str(booking.end_time),
        },
        limit=1,
    )
    if duplicates:
        raise api_errors.ConflictError(
            "An identical booking (same venue, date, start and end time) already exists",
            id=str(booking.id),
        )
    try:
        venue_booking_table.insert_one(booking.to_storage())
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return booking


def update(
    booking_id: schema.CampusID,
    description: str | object = UNSET,
    status: str | object = UNSET,
) -> campus.model.VenueBooking:
    """Patch a booking; given fields replace, absent fields stay.

    `description` is the purpose text; `status` moves the approval
    lifecycle (BOOKING_STATUSES). Who may send which field is the
    routes' decision — the resource applies both verbatim.

    Raises:
        api_errors.NotFoundError: If the booking does not exist.
        api_errors.InvalidRequestError: If no fields are given or a
            given status is outside the vocabulary.
    """
    if description is UNSET and status is UNSET:
        raise api_errors.InvalidRequestError(
            'Patch body required: send {"description": str} and/or {"status": "pending" | "approved" | "denied"}'
        )
    fields: dict[str, typing.Any] = {}
    if description is not UNSET:
        if not isinstance(description, str):
            raise api_errors.InvalidRequestError("description must be a string")
        fields["description"] = description
    if status is not UNSET:
        if not isinstance(status, str) or status not in BOOKING_STATUSES:
            raise api_errors.InvalidRequestError(
                "status must be one of: " + ", ".join(repr(s) for s in BOOKING_STATUSES)
            )
        fields["status"] = status
    get(booking_id)  # deterministic 404 before the write
    try:
        campus.model.VenueBooking.validate_update(fields)
    except ValueError as e:
        raise api_errors.InvalidRequestError(str(e)) from e
    try:
        venue_booking_table.update_by_id(str(booking_id), fields)
    except campus.storage.errors.NotFoundError:
        raise api_errors.NotFoundError(
            f"Booking not found: {booking_id}",
            id=str(booking_id),
        ) from None
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    # Read back rather than patching the local copy: the record's
    # shape is the table's business (created_at is server-owned).
    return get(booking_id)


def delete(booking_id: schema.CampusID) -> None:
    """Delete a booking.

    Raises:
        api_errors.NotFoundError: If the booking does not exist.
    """
    get(booking_id)  # deterministic 404 before the delete
    try:
        venue_booking_table.delete_by_id(str(booking_id))
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
