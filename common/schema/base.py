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
    NOT_ALLOWED = "Not allowed"  # Operation not allowed
    NOT_FOUND = "Not found"  # Record or data not found
    SUCCESS = "Success"  # Request successfully fulfilled
    VALID = "Valid"  # Input or data is valid


def translate_response(
        resp: Response,
        responseMap: dict[str, Response]
) -> Response | None:
    """Translate a response using a mapping of messages to responses.

    As responses bubble up the call stack, they may be translated to more
    specific responses using this function.

    Error statuses are returned as-is, as it is not expected for an
    error to be translated to a success. There is currently no mechanism
    to handle responses by status, only by message.

    Args:
        resp: The response to translate.
        responseMap: A mapping of messages to responses.

    Returns:
        The translated response, or None if no translation is found.
    """
    if resp.status == "error":
        return resp
    if resp.message in responseMap:
        return responseMap[resp.message]
    return None

