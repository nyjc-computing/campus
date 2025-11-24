"""campus.model.event

Event model definitions for Campus.
"""

from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import secret

from .base import Model


@dataclass(eq=False, kw_only=True)
class Event(Model):
    """Dataclass representation of a event record."""
    id: str = field(default_factory=secret.generate_access_code)
    # created_at inherited from Model
    name: str
    location: str | None = None
    location_url: str | None = None
    start_time: schema.DateTime | None = None
    duration: int | None = None
    description: str
