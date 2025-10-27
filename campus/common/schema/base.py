"""campus.common.schema.base

Base schema definitions, enums, and constants for Campus.
"""

from typing import Literal

ResponseStatus = Literal["ok", "error"]

# Common type aliases
Email = str
Url = str

# Campus types
CampusID = str
UserID = str
