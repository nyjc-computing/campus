"""campus.common.errors.validation

Field-level validation error support.

Reference: campus/api/docs/api-error-spec.md Section 5
"""

from typing import TypedDict

from .base import APIError, ErrorConstant


class FieldError(TypedDict):
    """A single field validation error.

    Attributes:
        field: The field name that failed validation
        code: Machine-readable error code (e.g., "INVALID_FORMAT", "MISSING")
        message: Human-readable error message
    """
    field: str
    code: str
    message: str


class ValidationError(APIError):
    """Validation error with field-level details.

    Used for request validation failures where multiple fields
    may have errors. Status code is 422 per the spec.

    Reference: campus/api/docs/api-error-spec.md Section 5
    """
    status_code: int = 422

    def __init__(
        self,
        message: str = "One or more fields are invalid",
        error_code: str = ErrorConstant.VALIDATION_FAILED,
        *,
        errors: list[FieldError] | None = None,
        **details
    ) -> None:
        """
        Args:
            message: Human-readable summary message
            error_code: Error constant (defaults to VALIDATION_FAILED)
            errors: List of field-specific errors
            **details: Additional metadata
        """
        self.field_errors: list[FieldError] = errors or []
        super().__init__(message, error_code, **details)

    def to_dict(self) -> dict[str, object]:
        """Convert to dict with errors array in addition to base envelope."""
        base = super().to_dict()
        if self.field_errors:
            base["error"]["errors"] = self.field_errors
        return base


__all__ = ["FieldError", "ValidationError"]
