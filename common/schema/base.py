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
    COMPLETED = "Completed"  # Completed without errors
    CREATED = "Created"  # Successfully created
    UPDATED = "Updated"  # Successfully updated
    DELETED = "Deleted"  # Successfully deleted
    EMPTY = "Empty"  # Record is empty
    EXPIRED = "Expired"  # Datetime is past
    FAILED = "Failed"  # Failed to complete
    FOUND = "Found"  # Record or data found
    INVALID = "Invalid"  # Invalid input or data
    NOT_FOUND = "Not found"  # Record or data not found
    SUCCESS = "Success"  # Request successfully fulfilled
    VALID = "Valid"  # Input or data is valid

