"""campus.api.resources.booking

Booking resource for Campus API.
"""

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
        """Create a new venue booking

        Arguments:
            user_id (schema.UserID)
                ID of the user making the booking.
            venue_id (schema.CampusID)
                ID of the venue being booked.
            description (schema.String)
                Description of the booking.
            start_time (schema.Time)
                Start time of the booking, HHMM format.
            end_time (schema.Time)
                End time of the booking, HHMM format.
            date (schema.Date)
                Date of the booking, ISO8601 format.

        Returns:
            model.VenueBooking: The created venue booking.
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
        """Get a full VenueBooking by ID.

        Returns:
            model.VenueBooking: The venue booking.

        Raises:
            NotFoundError: If the booking does not exist.
        """
        try:
            record = venue_booking_table.get_by_id(self.booking_id)
            venue_booking = model.VenueBooking.from_storage(record)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                "Booking not found",
                id=self.booking_id
            ) from None
        else:
            return venue_booking
    
    def update(self, description: schema.String) -> None:
        """Update fields of the booking.
        For now, only the description can be updated.
        To update other fields, the booking must be deleted and
        re-created with the new values.

        Args:
            description (schema.String):
            The new description for the booking.

        Raises:
            NotFoundError: If the booking does not exist.
        """
        try:
            model.VenueBooking.validate_update(
                {"description": description}
            )
        except ValueError as e:
            raise api_errors.InvalidRequestError(str(e)) from e

        try:
            venue_booking_table.update_by_id(
                self.booking_id,
                {"description": description}
            )
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                "Booking not found",
                id=self.booking_id
            ) from None

    def delete(self) -> None:
        """Delete the booking and all associated entries.

        Raises:
            NotFoundError: If the booking does not exist.
        """
        try:
            venue_booking_table.delete_by_id(self.booking_id)
        except campus.storage.errors.NotFoundError:
            raise api_errors.NotFoundError(
                "Booking not found",
                id=self.booking_id
            ) from None
