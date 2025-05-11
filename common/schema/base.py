"""common.schema.base

Base schema definitions, enums, and constants for Campus.
"""

from collections.abc import ItemsView
from typing import Any, Iterable, Iterator, Literal, Mapping

ResponseStatus = Literal["ok", "error"]


class Response(Mapping, Iterable):
    """Base interface for all responses.

    Responses support iteration (for unpacking) and property access.

    Modules using a Response object pattern should inherit from this class
    and override the `data` property to return the appropriate type(s).
    """
    # Use slots for performance purposes, since this class is used in many
    # places and is expected to be lightweight.
    # See https://docs.python.org/3.11/reference/datamodel.html#object.__slots__
    __slots__ = ("__",)

    def __init__(self, status: ResponseStatus, message: str, data: Any | None = None) -> None:
        self.__ = (status, message, data)

    @property
    def status(self) -> ResponseStatus:
        return self.__[0]
    
    @property
    def message(self) -> str:
        return self.__[1]
    
    @property
    def data(self) -> Any:
        return self.__[2]
    
    def __getitem__(self, key: int) -> Any:
        """Get an item by index."""
        return self.__[key]
    
    def __iter__(self) -> Iterator:
        """Iterate over the response."""
        return iter(self.__)
    
    def __len__(self) -> int:
        """Required by Mapping interface."""
        return len(self.__)
    
    def items(self) -> ItemsView[str, Any]:
        """Get the items of the response as an ItemsView."""
        return ItemsView({
            "status": self.status,
            "message": self.message,
            "data": self.data
        })


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
    # Client did not provide valid authentication credentials
    UNAUTHORIZED = "Unauthorized"
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
