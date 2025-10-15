"""campus.common.schema

Schema definitions, enums, and constants for Campus.
"""

__all__ = [
    "CampusID",
    "DatetimeStr",
    "CAMPUS_KEY",
    "UserID",
]

from .base import CampusID, DatetimeStr, UserID

CAMPUS_KEY = "id"
