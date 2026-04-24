"""campus.api.resources.booking

Booking resource for Campus API.
"""

import typing

from campus.common import schema
from campus.common.errors import api_errors
from campus.common.utils import uid
import campus.model as model
import campus.storage

venue_booking_table = campus.storage.get_table("venue_bookings")
venue_table = campus.storage.get_table("venues")


class BookingsResource:
    """Represents the bookings resource."""
    
    @staticmethod
    def init_storage() -> None:
        """Initialize storage."""
        venue_booking_table.init_from_model(
            "venue_bookings",
            model.VenueBooking
        )
        venue_table.init_from_model(
            "venues",
            model.Venue
        )

    def __getitem__(self, booking_id: schema.CampusID) -> "BookingResource":
        """Return a resource object for a specific timetable.

        Args:
            booking_id (schema.CampusID): ID of the booking.

        Returns:
            BookingResource: Resource representing the booking.
        """
        return BookingResource(booking_id)
    
    def new(
            self,
            user_id: schema.UserID,
            venue_id: schema.CampusID,
            description: schema.String,
            start_time: schema.Time,
            end_time: schema.Time,
            date: schema.Date,
    ) -> model.VenueBooking:
        """
            Create a new venue booking
            Updates the storage with the new venue booking
        """
        venue_booking = model.VenueBooking(
            id=schema.CampusID(
                uid.generate_category_uid("booking", length=8)
            ),
            user_id=schema.UserID(user_id),
            venue_id=schema.CampusID(venue_id),
            description=schema.String(description),
            start_time=schema.Time(start_time),
            end_time=schema.Time(end_time),
            date=schema.Date(date)
        )
        try:
            venue_booking_table.insert_one(venue_booking.to_storage())
        except campus.storage.errors.StorageError as e:
            raise api_errors.InternalError.from_exception(e) from e

        return venue_booking
        


class BookingResource:
    """Represents a single booking."""
    
    def __init__(self, booking_id: schema.CampusID):
        self.booking_id = booking_id

    def get(self) -> model.VenueBooking:
        """
        Get a full VenueBooking by ID.

        Returns:
            model.VenueBooking: The venue booking.

        Raises:
            ConflictError: If the booking does not exist.
        """
        try:
            record = venue_booking_table.get_by_id(self.booking_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Booking not found",
                    id=self.booking_id
                )
            venue_booking = model.VenueBooking.from_storage(record)
            return venue_booking
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Booking not found",
                id=self.booking_id
            ) from None
    
    def update(self, **updates: typing.Any) -> None:
        """Update fields of the booking.

        Args:
            **updates: Fields to update in the venue booking record.

        Raises:
            ConflictError: If the booking does not exist.
        """
        try:
            model.VenueBooking.validate_update(updates)

            record = venue_booking_table.get_by_id(self.booking_id)
            if record is None:
                raise api_errors.ConflictError(
                    "Booking not found",
                    id=self.booking_id
                )

            updated_record = {**record, **updates}
            venue_booking_table.update_by_id(self.booking_id, updated_record)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Booking not found",
                id=self.booking_id
            ) from None



    def delete(self) -> None:
        """Delete the booking and all associated entries.
    
        Raises:
            ConflictError: If the booking does not exist.
        """
        try:
            venue_booking_table.delete_by_id(self.booking_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.ConflictError(
                "Booking not found",
                id=self.booking_id
            ) from None

