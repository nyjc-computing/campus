"""campus.common.schema

Schema definitions, enums, and constants for Campus.
"""

__all__ = [
    "CAMPUS_KEY",
    "CampusID",
    "UserID",
    "Array",
    "Boolean",
    "DateTime",
    "Integer",
    "Number",
    "Object",
    "String",
]

from .base import (
    CampusID,
    UserID,
)

from .openapi import (
    Array,
    Boolean,
    DateTime,
    Integer,
    Number,
    Object,
    String,
)


from .base import CampusID, UserID

CAMPUS_KEY = "id"
