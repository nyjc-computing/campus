"""apps.common.models.base

Base types and classes for all Campus models.
"""

from typing import TypedDict

from common.schema import CampusID, UserID
from common.utils import utc_time


class BaseRecord(TypedDict):
    """Base class for all records in the Campus system.

    Records are Mapping objects that represent a single record in the database.
    BaseRecord reflects the keys that are common to all records in the system.
    """
    id: CampusID | UserID
    created_at: utc_time.datetime
