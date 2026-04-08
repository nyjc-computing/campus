"""campus.model.event

Event model definitions for Campus.
"""

from typing import ClassVar
from dataclasses import dataclass, field

from campus.common import schema
from campus.common.schema.openapi import String, DateTime
from campus.common.utils import uid

from .base import Model
from . import constraints

@dataclass(eq=False, kw_only=True)
class Event(Model):
    """
    Represents a single instance of an event.
    """
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("event", length=8)
    ))

    # Cosmetic fields
    name: String
    description: String
    location: String

    # Data fields
    location_url: String | None = None # Optional, online events only
    start_time: DateTime
    end_time: DateTime

    # No duplicate events allowed
    __constraints__ = constraints.Unique(
        "name", "description", "location", "location_url", "start_time", "end_time"
    )