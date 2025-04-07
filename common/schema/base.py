"""common.schema.base

Base schema definitions, enums, and constants for Campus.
"""

from typing import Any, Literal, Protocol


class Response(Protocol):
    """Common interface for all responses."""
    status: Literal["ok", "error"]
    message: str
    data: Any | None = None


class Message:
    """Constants of common response messages."""
    CREATED = "Created"
    UPDATED = "Updated"
    DELETED = "Deleted"
    EXPIRED = "Expired"
    FAILED = "Failed"
    FOUND = "Found"
    INVALID = "Invalid"
    NOT_FOUND = "Not found"
    SUCCESS = "Success"
    VALID = "Valid"

