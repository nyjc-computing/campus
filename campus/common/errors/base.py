"""campus.common.errors.base

Base error definitions, enums, and constants for Campus.
These errors are used to catch common API errors and return
standardised JSON responses.
"""

from typing import Any

JsonValues = int | float | str | bool | None
JsonList = list[JsonValues]
JsonDict = dict[str, JsonValues]


class ErrorConstant(str):
    """Error enums"""
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    SERVER_ERROR = "SERVER_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"


class APIError(Exception):
    """Base class for all API errors.

    This class is used to catch common API errors and return
    standardised JSON responses.
    """
    status_code: int
    message: str
    error_code: ErrorConstant
    details: JsonDict

    def __init__(
            self,
            message: str,
            error_code: str,
            **details
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = ErrorConstant(error_code)
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Convert the error to a dictionary.

        This function is used to convert the error to a dictionary
        for JSON serialisation.
        """
        err_obj = {
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }
        # We can't use campus.common.devops to do a env check here because
        # it would create a circular import.
        # Pop the traceback in production environment.
        if 500 <= self.status_code < 600:
            import traceback
            err_obj.update(traceback=traceback.format_exc())
        return err_obj
