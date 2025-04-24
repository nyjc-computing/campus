"""apps.palmtree.errors.base.py

Base error definitions, enums, and constants for Palmtree.
These errors are used to catch common API errors and return
standardised JSON responses.
"""

from typing import Any

JsonValues = int | float | str | bool | None
JsonList = list[JsonValues]
JsonDict = dict[str, JsonValues]


class ErrorConstant(str):
    INVALID_REQUEST = "INVALID_REQUEST"
    SERVER_ERROR = "SERVER_ERROR"


class APIError(Exception):
    """Base class for all API errors.

    This class is used to catch common API errors and return
    standardised JSON responses.
    """
    status_code: int = 500
    message: str
    error_code: ErrorConstant
    details: JsonDict

    def __init__(
            self,
            message: str,
            error_code: str = ErrorConstant.SERVER_ERROR,
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
        return {
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
        }


