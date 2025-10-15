"""campus.models.base

Base types and classes for all Campus models.
"""

from typing import TypedDict

from campus.common import schema


class BaseRecord(TypedDict):
    """Base class for all records in the Campus system.

    Records are Mapping objects that represent a single record in the database.
    BaseRecord reflects the keys that are common to all records in the system.
    """
    id: schema.CampusID | schema.UserID
    created_at: schema.DatetimeStr
