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
    # Device Authorization Flow errors (RFC 8628)
    "authorization_pending",
    "slow_down",
    "expired_token",
    "access_denied",
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
    # Device Authorization Flow errors (RFC 8628)
    "authorization_pending",
    "slow_down",
    "expired_token",
    "access_denied",
)

# Mapping of OAuth error strings to Campus error codes
# Used for envelope format conversion
_OAUTH_TO_CAMPUS_ERROR_CODES: dict[str, str] = {
    "unsupported_grant_type": "AUTH_UNSUPPORTED_GRANT",
    "unsupported_response_type": "AUTH_UNSUPPORTED_RESPONSE_TYPE",
}


class ErrorConstant(str):
    """Error enums.

    Error codes follow the API Error Handling Specification:
    - UPPER_SNAKE_CASE format
    - Stable across versions
    - Documented and machine-readable

    Reference: campus/api/docs/api-error-spec.md
    """
    # General API errors
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"

    # Validation errors
    VALIDATION_FAILED = "VALIDATION_FAILED"

    # OAuth/Auth errors
    AUTH_INVALID_REQUEST = "AUTH_INVALID_REQUEST"
    AUTH_INVALID_CLIENT = "AUTH_INVALID_CLIENT"
    AUTH_INVALID_GRANT = "AUTH_INVALID_GRANT"
    AUTH_UNAUTHORIZED_CLIENT = "AUTH_UNAUTHORIZED_CLIENT"
    AUTH_UNSUPPORTED_GRANT = "AUTH_UNSUPPORTED_GRANT"
    AUTH_UNSUPPORTED_RESPONSE_TYPE = "AUTH_UNSUPPORTED_RESPONSE_TYPE"
    AUTH_INVALID_SCOPE = "AUTH_INVALID_SCOPE"
    AUTH_ACCESS_DENIED = "AUTH_ACCESS_DENIED"
    AUTH_SERVER_ERROR = "AUTH_SERVER_ERROR"
    AUTH_TEMPORARILY_UNAVAILABLE = "AUTH_TEMPORARILY_UNAVAILABLE"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_INSUFFICIENT_SCOPE = "AUTH_INSUFFICIENT_SCOPE"

    # Additional specific error codes can be added here as needed


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

        Returns a spec-compliant error envelope:
        {
            "error": {
                "code": "ERROR_CODE",
                "message": "Human-readable explanation",
                "details": {},
                "request_id": null
            }
        }

        Reference: campus/api/docs/api-error-spec.md
        """
        error_obj: dict[str, Any] = {
            "code": str(self.error_code),
            "message": self.message,
        }

        # Only include details if non-empty
        if self.details:
            error_obj["details"] = dict(self.details)

        # Add traceback in development mode for server errors
        # We can't use campus.common.devops to do an env check here
        # because it would create a circular import.
        if 500 <= self.status_code < 600:
            import os
            if os.getenv("ENV", "development") == "development":
                import traceback
                if not self.details:
                    error_obj["details"] = {}
                error_obj["details"]["traceback"] = traceback.format_exc()

        # request_id will contain a correlation ID once request tracing is implemented
        error_obj["request_id"] = None

        return {"error": error_obj}


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

    def to_dict(self, envelope_format: bool = False) -> dict[str, Any]:
        """Convert the error to a dictionary.

        This function is used to convert the error to a dictionary
        for JSON serialisation.

        Args:
            envelope_format: If True, use Campus error envelope.
                           If False, use RFC 6749 format (default).

        Returns:
            RFC 6749 format by default, Campus envelope when requested.
        """
        if envelope_format:
            # Campus envelope for API consistency
            # Map OAuth errors to Campus error codes following auth-error-spec.md
            campus_code = _OAUTH_TO_CAMPUS_ERROR_CODES.get(
                self.error,
                f"AUTH_{self.error.upper()}"
            )
            return {
                "error": {
                    "code": campus_code,
                    "message": self.error_description,
                    "details": {
                        "oauth_error": self.error,
                        "oauth_error_description": self.error_description,
                        **self.details
                    },
                    "request_id": None
                }
            }
        # RFC 6749 format (default for OAuth compliance)
        err_obj = {
            "error": self.error,
            "error_description": self.error_description,
            "error_uri": self.error_uri,
            "details": self.details,
        }
        return err_obj
