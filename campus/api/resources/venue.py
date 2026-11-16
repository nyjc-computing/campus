"""campus.api.resources.venue

Venue resource for Campus API: bookable campus venues stored as
documents (campus#1099).

The venue schema is deliberately fluid: each venue carries freeform
`metadata` — the facts (name, type, capacity, location, ...) live here
until they stabilise — and freeform markdown `notes`. Storage is the
documents backend, so the metadata shape can drift without migrations;
stable metadata fields will be hoisted into campus.model.Venue fields
as they settle.

Boundary (as with subjcombi): the resources stay ungated for
in-process callers; the routes gate mutations on the `venues.admin`
role circle (docs/circles-access-control.md).
"""

import typing

import campus.model
import campus.storage
from campus.common import schema
from campus.common.errors import api_errors

# Sentinel for "field not given" in PATCH bodies: JSON null is
# meaningful for `notes` (clears it), so absence needs its own marker.
UNSET = object()

venue_collection = campus.storage.get_collection("venues")


def to_resource(venue: campus.model.Venue) -> dict:
    """Project a venue into its API resource form."""
    return venue.to_resource()


def get(venue_id: schema.CampusID) -> campus.model.Venue:
    """Get a venue by ID.

    Raises:
        api_errors.NotFoundError: If the venue does not exist.
    """
    try:
        record = venue_collection.get_by_id(str(venue_id))
    except campus.storage.errors.NotFoundError:
        record = None
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    # get_by_id signals absence with None (and some backends raise
    # NotFoundError instead) — both are a 404 here.
    if record is None:
        raise api_errors.NotFoundError(
            f"Venue not found: {venue_id}",
            id=str(venue_id),
        )
    return campus.model.Venue.from_storage(record)


def list_all() -> list[campus.model.Venue]:
    """All venues, oldest first.

    Venue counts are small (a campus's rooms and spaces), so there is
    no pagination; callers filter client-side.
    """
    try:
        records = venue_collection.get_matching(
            {},
            order_by="created_at",
            ascending=True,
        )
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return [campus.model.Venue.from_storage(r) for r in records]


def new(
        metadata: dict[str, typing.Any] | None = None,
        notes: str | None = None,
) -> campus.model.Venue:
    """Create a venue with the given initial metadata and notes.

    Both fields are optional: an unnamed venue (empty metadata, no
    notes) is valid and gains its facts through PATCH as they are
    decided.
    """
    venue = campus.model.Venue(
        metadata=dict(metadata or {}),
        notes=notes,
    )
    try:
        venue_collection.insert_one(venue.to_storage())
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return venue


def update(
        venue_id: schema.CampusID,
        metadata: dict[str, typing.Any] | object = UNSET,
        notes: str | None | object = UNSET,
) -> campus.model.Venue:
    """Patch a venue; given fields replace, absent fields stay.

    `metadata` replaces the whole dict — merging partial metadata is
    the caller's job (read, merge, PATCH). `notes=None` clears the
    note. The venue's `updated_at` stamp is refreshed on every call.

    Raises:
        api_errors.NotFoundError: If the venue does not exist.
        api_errors.InvalidRequestError: If no fields are given, or a
            given field has the wrong shape.
    """
    if metadata is UNSET and notes is UNSET:
        raise api_errors.InvalidRequestError(
            "Patch body required: send {\"metadata\": {...}} and/or "
            "{\"notes\": str | null}"
        )
    venue = get(venue_id)
    new_metadata: dict[str, typing.Any] = venue.metadata
    new_notes: str | None = venue.notes
    if metadata is not UNSET:
        if not isinstance(metadata, dict):
            raise api_errors.InvalidRequestError(
                "metadata must be an object"
            )
        new_metadata = dict(metadata)
    if notes is not UNSET:
        if notes is None:
            new_notes = None
        elif isinstance(notes, str):
            new_notes = notes
        else:
            raise api_errors.InvalidRequestError(
                "notes must be a string or null"
            )
    updated = campus.model.Venue(
        id=venue.id,
        created_at=venue.created_at,
        metadata=new_metadata,
        notes=new_notes,
        updated_at=schema.DateTime.utcnow(),
    )
    try:
        venue_collection.update_by_id(
            str(venue_id),
            updated.to_storage(),
        )
    except campus.storage.errors.NotFoundError:
        raise api_errors.NotFoundError(
            f"Venue not found: {venue_id}",
            id=str(venue_id),
        ) from None
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
    return updated


def delete(venue_id: schema.CampusID) -> None:
    """Delete a venue.

    Bookings that reference the venue are out of scope: the bookings
    surface is still 501-stubbed, so no live references can dangle.

    Raises:
        api_errors.NotFoundError: If the venue does not exist.
    """
    get(venue_id)  # deterministic 404 before the delete
    try:
        venue_collection.delete_by_id(str(venue_id))
    except campus.storage.errors.StorageError as e:
        raise api_errors.InternalError.from_exception(e) from e
