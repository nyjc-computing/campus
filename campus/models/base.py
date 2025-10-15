"""campus.models.base

Base types and classes for all Campus models.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Self, Type, TypedDict

from campus.common import schema


class BaseRecordDict(TypedDict):
    """Base class for all records in the Campus system.

    Records are Mapping objects that represent a single record in the database.
    BaseRecord reflects the keys that are common to all records in the system.
    """
    id: schema.CampusID | schema.UserID
    created_at: schema.DatetimeStr


# Issue 201: refactoring to dataclasses
# See https://github.com/nyjc-computing/campus/issues/201
@dataclass(eq=False, kw_only=True)
class BaseRecord:
    """Base class for all record models in Campus.
    
    Subclasses are expected to provide their own CampusID factories.
    """
    id: schema.CampusID = field(init=True)
    created_at: schema.DateTime = field(default_factory=schema.DateTime.utcnow)

    @classmethod
    def from_dict(cls: Type[Self], data: dict) -> Self:
        """Create a record from a dictionary."""
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a dictionary."""
        return asdict(self)


@dataclass(eq=False, kw_only=True)
class UserRecord(BaseRecord):
    """Base class for user records in Campus."""
    id: schema.UserID = field(init=True)
    id: schema.CampusID | schema.UserID
