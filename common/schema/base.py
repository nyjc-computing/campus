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
    """Constants of common response messages.
    
    These messages are used to differentiate the possible outcomes of "ok" or "error" responses.
    """
    # Operation completed without errors (in absence of more specific message)
    COMPLETED = "Completed"
    # Successfully created
    CREATED = "Created"
    # Successfully updated
    UPDATED = "Updated"
    # Successfully deleted
    DELETED = "Deleted"
    # Successful with empty result
    EMPTY = "Empty"
    # Datetime is past
    EXPIRED = "Expired"
    # Failed to complete - standard message for "error"
    FAILED = "Failed"
    # Record or data found
    FOUND = "Found"
    # Invalid input or data
    INVALID = "Invalid"
    # Operation possible but not allowed
    NOT_ALLOWED = "Not allowed"
    # Record or data not found
    NOT_FOUND = "Not found"
    # Request successfully fulfilled (all operations complete)
    SUCCESS = "Success"
    # Input or data is valid
    VALID = "Valid"


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

