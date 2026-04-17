from dataclasses import dataclass, field
from typing import Any, Self

from campus.common import schema
from campus.common.utils import uid

from .base import Model
from . import constraints

@dataclass(eq=False, kw_only=True)
class VenueBooking(Model):
    """
    Represents a booking for a venue on a specific date and time.

    Fields:
      id (CampusID): Unique identifier for the booking.
      user_id (UserID): FK referencing the user who made the booking.
      venue_id (CampusID): FK referencing the venue being booked.
      description (String): Description or purpose of the booking.
      start_time (Time): Start time of the booking.
      end_time (Time): End time of the booking.
      date (Date): Date of the booking.

    Constraints:
      - Unique by venue_id, date, start_time, and end_time to prevent exact duplicate bookings.
      Overlap checking must be conducted separately.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("booking", length=8)
    ))
    user_id: schema.UserID
    venue_id: schema.CampusID
    description: schema.String
    start_time: schema.Time
    end_time: schema.Time
    date: schema.Date
    # NOTE: This only prevents exact duplicate bookings.
    # Overlap checking must still be conducted separately
    __constraints__ = constraints.Unique("venue_id", "date", "start_time", "end_time")


@dataclass(eq=False, kw_only=True)
class Venue(Model):
    """
    Represents a venue that can be booked.

    Fields:
      id (CampusID): Unique identifier for the venue.
      venue_name (String): Name of the venue.

    Note:
      Other model fields to be confirmed (TBC).
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("venue", length=8)
    ))
    venue_name: schema.String
    venue_type: schema.String
  