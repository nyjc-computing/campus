from dataclasses import dataclass, field
from typing import Any, Self

from campus.common import schema
from campus.common.utils import uid

from .base import Model
from . import constraints

@dataclass(eq=False, kw_only=True)
class VenueBooking(Model):
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("booking", length=8)
    ))
    user_id: schema.UserID
    venue_id: schema.CampusID
    description: schema.String
    start_time: schema.Time
    end_time: schema.Time
    date: schema.Date
    # NOTE: This only prevents exact duplicate bookings. Overlap checking must still be conducted separately
    __constraints__ = constraints.Unique("venue_id", "date", "start_time", "end_time")

@dataclass(eq=False, kw_only=True)
class Venue(Model):
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("venue", length=8)
    ))
    venue_name: schema.String
    # NOTE: Other model fields TBC
