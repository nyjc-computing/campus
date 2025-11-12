"""campus.model.circle

Circle model for the Campus API.

This module defines circles (organizational units/groups) for the Campus API.
"""

from dataclasses import dataclass, field

from campus.common import schema
from campus.common.utils import uid

from .base import Model


@dataclass(eq=False, kw_only=True)
class Circle(Model):
    """Dataclass representation of a circle record."""
    id: schema.CampusID = field(default_factory=(
        lambda: uid.generate_category_uid("circle", length=8)
    ))
    # created_at inherited from Model
    name: str
    description: str = ""
    tag: str  # CircleTag type alias from models
    members: dict[schema.CampusID, int] = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
