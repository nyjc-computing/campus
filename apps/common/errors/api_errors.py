"""apps.palmtree.errors.api.py

API error definitions for Palmtree.
These errors represent all possible API errors that would be raised.
"""
from .base import APIError, ErrorConstant


def raise_api_error(status: int, **body) -> None:
    """Raise an API error with the given status code."""
    match status:
        case 400:
            raise InvalidRequestError(
                message="Bad request",
                status=status,
                **body
            )
        case 401:
            raise UnauthorizedError(
                message="Unauthorized",
                status=status,
                **body
           )
        case 409:
            raise ConflictError(
                message="Conflict",
                status=status,
                **body
            )
        case 415:
            raise UnsupportedMediaTypeError(
                message="Unsupported Media Type",
                status=status,
                **body
            )
        case 500:
            raise InternalError(
                message="Internal server error",
                status=status,
                **body
            )
        case _:
            raise ValueError(
                f"Unexpected status code: {status}"
            )


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


class ConflictError(APIError):
    """Conflict error.

    Error indicates that the request conflicts with the current state of the
    server.
    E.g. trying to create a resource that already exists, delete a resource
      that does not exist, etc.
    """
    status_code: int = 409

    def __init__(
            self,
            message: str = "Conflict",
            error_code: str = ErrorConstant.CONFLICT,
            **details
    ) -> None:
        super().__init__(message, error_code, **details)


class UnsupportedMediaTypeError(APIError):
    """Unsupported Media Type error.

    Error indicates that the request's Content-Type is not supported by the server.
    Specifically, the server expects 'application/json'.
    """
    status_code: int = 415

    def __init__(
            self,
            message: str = "Unsupported Media Type: Content-Type must be 'application/json'",
            error_code: str = ErrorConstant.INVALID_REQUEST,
            **details
    ) -> None:
        super().__init__(message, error_code, **details)
