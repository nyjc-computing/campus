"""apps.palmtree.errors.api.py

API error definitions for Palmtree.
These errors represent all possible API errors that would be raised.
"""
from .base import APIError, ErrorConstant


class InternalError(APIError):
    """Internal server error.

    Error indicates that the server encountered an unexpected condition
    that prevented it from fulfilling the request.
    """
    status_code: int = 500

    def __init__(
            self,
            message: str = "Internal server error",
            error_code: str = ErrorConstant.SERVER_ERROR,
            **details
    ) -> None:
        super().__init__(message, error_code, **details)


class InvalidRequestError(APIError):
    """Invalid request error.

    Error indicates that the request does not follow the requirements.
    E.g. missing fields, invalid data types, etc.
    """
    status_code: int = 400

    def __init__(
            self,
            message: str = "Invalid request",
            error_code: str = ErrorConstant.INVALID_REQUEST,
            **details
    ) -> None:
        super().__init__(message, error_code, **details)


class UnauthorizedError(APIError):
    """Unauthorized error.

    Error indicates that the request is not authenticated.
    E.g. missing authentication token, invalid token, etc.
    """
    status_code: int = 401

    def __init__(
            self,
            message: str = "Unauthorized",
            error_code: str = ErrorConstant.INVALID_REQUEST,
            **details
    ) -> None:
        super().__init__(message, error_code, **details)