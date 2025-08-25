"""campus.models.base

Base types and classes for all Campus models.
"""

from dataclasses import dataclass, field
from typing import TypedDict

from campus.common.schema import CampusID, DateTime, UserID
from campus.common.utils import utc_time


class BaseRecordDict(TypedDict):
    """Base class for all records in the Campus system.

    Records are Mapping objects that represent a single record in the database.
    BaseRecord reflects the keys that are common to all records in the system.
    """
    id: CampusID | UserID
    created_at: utc_time.datetime


# Issue 201: refactoring to dataclasses
# See https://github.com/nyjc-computing/campus/issues/201
@dataclass(eq=False, kw_only=True)
class BaseRecord:
    """Base class for all record models in Campus.
    
    Subclasses are expected to provide their own CampusID factories.
    """
    id: CampusID = field(init=True)
    created_at: DateTime = field(default_factory=DateTime.utcnow)


@dataclass(eq=False, kw_only=True)
class UserRecord:
    """Base class for user records in Campus."""
    id: UserID = field(init=True)
    created_at: DateTime = field(default_factory=DateTime.utcnow)
