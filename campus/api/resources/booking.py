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


# Interface
# campus.api.booking.new()
# campus.api.booking[booking_id].get()
# campus.api.booking[booking_id].update()
# campus.api.booking[booking_id].delete()


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
            metadata: dict[str, typing.Any],
            lessongroups: typing.List[dict[str, typing.Any]],
    ) -> model.Timetable:
        """Create a new timetable with metadata and entries.

        `lessongroups` is a list of dicts following the schema:
        - label [str]
        - members list[str]
        - entries list[dict]

        Each entry has:
        - venue Optional[str]
        - weekday [str]
        - timeslot [str]
        """



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

    
    def update(self, **updates: typing.Any) -> None:
        """Update fields of the booking.

        Args:
            **updates: Fields to update in the venue booking record.
        """


    def delete(self) -> None:
        """Delete the booking and all associated entries.
    
        Raises:
            ConflictError: If the booking does not exist.
        """


