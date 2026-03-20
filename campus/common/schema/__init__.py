"""campus.common.schema

Schema definitions, enums, and constants for Campus.
"""

__all__ = [
    "CAMPUS_KEY",
    "Array",
    "Boolean",
    "CampusID",
    "Date",
    "DateTime",
    "Email",
    "Integer",
    "Number",
    "Object",
    "String",
    "Url",
    "UserID",
]

from .base import (
    CampusID,
    UserID,
)

from .openapi import (
    Array,
    Boolean,
    Date,
    DateTime,
    Email,
    Integer,
    Number,
    Object,
    String,
    Url,
)

CAMPUS_KEY = "id"
