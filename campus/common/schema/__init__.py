"""campus.common.schema

Schema definitions, enums, and constants for Campus.
"""

from .base import (
    CampusID,
    UserID,
)

from .openapi import (
    Boolean,
    Integer,
    Number,
    String,
    DateTime,
    Array,
    Object,
)


__all__ = [
    "CampusID",
    "UserID",
    "Boolean",
    "Integer",
    "Number",
    "String",
    "DateTime",
    "Array",
    "Object",
]
