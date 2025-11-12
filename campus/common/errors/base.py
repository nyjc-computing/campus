"""campus.common.errors.base

Base error definitions, enums, and constants for Campus.
These errors are used to catch common API errors and return
standardised JSON responses.
"""

__all__ = (
    "APIError",
    "OAuthError",
    "ErrorConstant",
    "AUTH_RESPONSE_ERROR_TYPES",
    "TOKEN_RESPONSE_ERROR_TYPES",
)


from typing import Any, Literal

JsonValues = int | float | str | bool | None
JsonList = list[JsonValues]
JsonDict = dict[str, JsonValues]

AuthResponseErrorType = Literal[
    "invalid_request",
    "unauthorized_client",
    "access_denied",
    "unsupported_response_type",
    "invalid_scope",
    "server_error",
    "temporarily_unavailable",
]
TokenResponseErrorType = Literal[
    "invalid_request",
    "invalid_client",
    "invalid_grant",
    "unauthorized_client",
    "unsupported_grant_type",
    "invalid_scope",
]
AUTH_RESPONSE_ERROR_TYPES = (
    "invalid_request",
    "unauthorized_client",
    "access_denied",
    "unsupported_response_type",
    "invalid_scope",
    "server_error",
    "temporarily_unavailable",
)
TOKEN_RESPONSE_ERROR_TYPES = (
    "invalid_request",
    "invalid_client",
    "invalid_grant",
    "unauthorized_client",
    "unsupported_grant_type",
    "invalid_scope",
)


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
        # We can't use campus.common.devops to do a env check here
        # because it would create a circular import.
        # Pop the traceback in production environment.
        if 500 <= self.status_code < 600:
            import traceback
            err_obj.update(traceback=traceback.format_exc())
        return err_obj


class OAuthError(Exception):
    """Base class for all OAuth errors.

    This class is used to catch common OAuth errors and return
    standardised JSON responses.
    Follows RFC 6749 Section 5.2
    https://datatracker.ietf.org/doc/html/rfc6749#section-5.2
    """
    status_code: int = 400
    error: AuthResponseErrorType | TokenResponseErrorType
    error_description: str
    error_uri: str | None
    details: JsonDict

    def __init__(
            self,
            error_description: str,
            error_uri: str | None = None,
            **details
    ) -> None:
        super().__init__(error_description)
        self.error_description = error_description
        self.error_uri = error_uri
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Convert the error to a dictionary.

        This function is used to convert the error to a dictionary
        for JSON serialisation.
        """
        err_obj = {
            "error": self.error,
            "error_description": self.error_description,
            "error_uri": self.error_uri,
            "details": self.details,
        }
        return err_obj
