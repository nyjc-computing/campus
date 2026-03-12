"""campus.common.schema.base

Base schema definitions, enums, and constants for Campus.
"""

from typing import Literal

from . import openapi

ResponseStatus = Literal["ok", "error"]

# Campus types
CampusID = openapi.String
UserID = openapi.Email
