"""campus.common.schema.base

Base schema definitions, enums, and constants for Campus.
"""

from typing import Literal

ResponseStatus = Literal["ok", "error"]


# TODO: Replace with OpenAPI-based pattern-string schema
CampusID = str
UserID = str
