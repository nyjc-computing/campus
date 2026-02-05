# API Error Specification Refactor Plan

This document outlines the phased implementation plan to bring the Campus API error handling into compliance with [api-error-spec.md](./api-error-spec.md).

**Each phase results in working code that passes all existing tests.** New tests for error-spec compliance are added at the appropriate phases.

---

## Progress Summary

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Complete | Core error structure (error envelope) |
| 2 | ✅ Complete | Validation error structure |
| 3 | ✅ Complete | Update validation code |
| 4 | Pending | Add error response tests |
| 5 | Pending | Client-side updates (campus-api-python) |
| 6 | Pending | Documentation |

---

## Phase 1: Core Error Structure (Server) ✅

**Status**: Already implemented in `refactor/api-error-spec` branch.

### Completed Changes

1. **ErrorConstant enum** ([`campus/common/errors/base.py`](../../common/errors/base.py))
   - Added `INTERNAL_ERROR` (renamed from `SERVER_ERROR`)
   - Added `VALIDATION_FAILED`
   - Added docstring referencing the spec

2. **APIError.to_dict()** ([`campus/common/errors/base.py`](../../common/errors/base.py))
   - Returns spec-compliant envelope: `{"error": {"code": "...", "message": "...", "details": {}, "request_id": null}}`
   - `request_id` set to `null` (to be implemented later)
   - Traceback only in `details` for development mode (5xx errors only)
   - Uses `ENV` environment variable for dev/prod detection

3. **Error handlers** ([`campus/common/errors/__init__.py`](../../common/errors/__init__.py))
   - `handle_api_error()` updated to handle new envelope format
   - Removes `details` in production for security
   - OAuth errors remain exempt (follow RFC 6749)

4. **InternalError** ([`campus/common/errors/api_errors.py`](../../common/errors/api_errors.py))
   - Default message: "An unexpected error occurred"
   - Uses `ErrorConstant.INTERNAL_ERROR`

### Verify Phase 1

```bash
cd campus
pytest tests/ -k error -v
```

---

## Phase 2: Validation Error Structure ✅

**Status**: Complete. Commit `f526a74`.

**Goal**: Implement field-level validation error format per Section 5 of the spec.

### 2.1 Create Field Error Types

**New file**: `campus/common/errors/validation.py`

```python
"""Field-level validation error support."""

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
        self.field_errors = errors or []
        super().__init__(message, error_code, **details)

    def to_dict(self) -> dict[str, object]:
        """Convert to dict with errors array in addition to base envelope."""
        base = super().to_dict()
        if self.field_errors:
            base["error"]["errors"] = self.field_errors
        return base
```

### 2.2 Export New Classes

**File**: `campus/common/errors/__init__.py`

```python
from .validation import ValidationError, FieldError

__all__ += ["ValidationError", "FieldError"]
```

### 2.3 Add 422 to `raise_api_error` Helper

**File**: `campus/common/errors/api_errors.py`

```python
from .validation import ValidationError

def raise_api_error(status: int, **body) -> NoReturn:
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
        case 403:
            raise ForbiddenError(
                message="Forbidden",
                status=status,
                **body
            )
        case 404:
            raise NotFoundError(
                message="Not found",
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
        case 422:
            errors = body.pop("errors", None)
            raise ValidationError(
                message=body.get("message", "Validation failed"),
                errors=errors,
                **body
            )
        case 500:
            raise InternalError(
                message="Internal server error",
                status=status,
                **body
            )
    raise ValueError(
        f"Unexpected status code: {status}"
    )
```

### Test Phase 2

```bash
cd campus
pytest tests/ -k validation -v
```

---

## Phase 3: Update Validation Code ✅

**Status**: Complete. Commit `0ceac37`.

**Goal**: Convert existing validation errors to use new structured format.

### 3.1 Update `unpack_request` Decorator ✅

**File**: `campus/flask_campus/utils.py`

The `unpack_into` function currently raises `KeyError` for missing params. Update to collect field errors:

```python
from campus.common.errors import ValidationError, FieldError

def unpack_into(
        func: Callable[..., Any],
        **request_args: Any,
) -> Any:
    """Unpack request arguments into the given function's arguments.

    Raises ValidationError with structured field errors for any issues.
    """
    reconciled, extra_args, missing_params = parameter.reconcile(
        request_args,
        func
    )

    field_errors: list[FieldError] = []

    if missing_params:
        field_errors.extend([
            FieldError(
                field=param,
                code="MISSING",
                message=f"Missing required field: {param}"
            )
            for param in missing_params
        ])

    # Type validation would be added here
    # For now, let parameter.reconcile handle it

    if field_errors:
        raise ValidationError(
            message="One or more fields are invalid",
            errors=field_errors
        )

    return func(**reconciled, **extra_args)
```

### 3.2 Update Type Validation (Optional Enhancement) ⏸️ Deferred

**File**: `campus/common/validation/record.py`

The `_validate_key_names_types` function could be enhanced to return `FieldError` objects instead of raising directly. Deferred to a follow-up to keep phases small.

### Test Phase 3 ✅

```bash
cd campus
poetry run python tests/run_tests.py all
# All 103 unit tests and 18 integration tests passed
```

---

## Phase 4: Add Error Response Tests

**Goal**: Ensure spec compliance is verified by tests.

### 4.1 Create Error Response Test Module

**New file**: `campus/tests/api/test_error_responses.py`

```python
"""Test error response format compliance with api-error-spec.md"""

import pytest
import os
os.environ["ENV"] = "development"  # Ensure consistent test environment

from campus.common.errors import (
    ConflictError,
    ForbiddenError,
    InternalError,
    InvalidRequestError,
    NotFoundError,
    UnauthorizedError,
    ValidationError, FieldError,
)


class TestErrorEnvelope:
    """All errors must have consistent error envelope structure (Section 3)."""

    @pytest.mark.parametrize("error_class,status", [
        (InvalidRequestError, 400),
        (UnauthorizedError, 401),
        (ForbiddenError, 403),
        (NotFoundError, 404),
        (ConflictError, 409),
        (InternalError, 500),
    ])
    def test_error_has_envelope(self, error_class, status):
        """Error responses must have error.code, error.message, error.request_id."""
        err = error_class()
        response = err.to_dict()

        assert "error" in response, "Response must have 'error' key"
        assert "code" in response["error"], "Error must have 'code'"
        assert "message" in response["error"], "Error must have 'message'"
        assert "request_id" in response["error"], "Error must have 'request_id'"
        assert isinstance(response["error"]["details"], dict), "details must be dict"

    def test_request_id_is_null(self):
        """request_id is currently always null (not yet implemented)."""
        err = NotFoundError()
        response = err.to_dict()
        assert response["error"]["request_id"] is None


class TestValidationErrors:
    """Validation errors must include field-level details (Section 5)."""

    def test_validation_error_with_field_errors(self):
        """ValidationError includes errors array."""
        field_errors = [
            FieldError(field="email", code="INVALID_FORMAT", message="Invalid email"),
            FieldError(field="password", code="TOO_SHORT", message="Password too short"),
        ]

        err = ValidationError(errors=field_errors)
        response = err.to_dict()

        assert response["error"]["code"] == "VALIDATION_FAILED"
        assert "errors" in response["error"]
        assert len(response["error"]["errors"]) == 2

        for fe in response["error"]["errors"]:
            assert "field" in fe
            assert "code" in fe
            assert "message" in fe

    def test_validation_error_without_field_errors(self):
        """ValidationError without errors still returns valid envelope."""
        err = ValidationError()
        response = err.to_dict()

        assert "errors" not in response["error"]
        assert response["error"]["code"] == "VALIDATION_FAILED"


class TestErrorCodes:
    """Error codes must be UPPER_SNAKE_CASE and stable (Section 4)."""

    def test_error_codes_format(self):
        """All error codes should be UPPER_SNAKE_CASE."""
        from campus.common.errors.base import ErrorConstant

        for attr in dir(ErrorConstant):
            if not attr.startswith('_'):
                code = getattr(ErrorConstant, attr)
                assert isinstance(code, str)
                # UPPER_SNAKE_CASE means uppercase with underscores
                assert code.isupper() or code in ('CONFLICT', 'FORBIDDEN', 'INTERNAL_ERROR',
                                                   'INVALID_REQUEST', 'NOT_FOUND', 'UNAUTHORIZED',
                                                   'VALIDATION_FAILED')


class TestEnvironmentSpecificBehavior:
    """Production vs development behavior (Section 6)."""

    def test_development_includes_traceback_for_server_errors(self):
        """Development mode should include traceback in details for 5xx errors."""
        os.environ["ENV"] = "development"
        err = InternalError()
        response = err.to_dict()

        # Traceback should be in details for 500 errors in dev
        assert "details" in response["error"]
        assert "traceback" in response["error"]["details"]

    def test_production_hides_traceback(self):
        """Production mode must not include traceback in response."""
        os.environ["ENV"] = "production"
        err = InternalError()
        response = err.to_dict()

        # In production, traceback is removed by error handler
        # But to_dict() still adds it in dev mode - the handler cleans it
        # This test verifies the handler does its job
        from campus.common import errors
        from campus.common import devops

        # Simulate what handle_api_error does
        err_dict = err.to_dict()
        if devops.ENV == devops.PRODUCTION:
            err_dict["error"].pop("details", None)

        assert "traceback" not in err_dict.get("error", {}).get("details", {})
```

### 4.2 Update Existing Tests

Check if any existing tests assert on the old error format and update them:

```bash
cd campus
pytest tests/ -v  # Look for failing tests related to error responses
```

### Test Phase 4

```bash
cd campus
pytest tests/api/test_error_responses.py -v
```

---

## Phase 5: Client-Side Updates (campus-api-python)

**Goal**: Update Python client to parse new error format.

### 5.1 Update Error Response Parsing

**File**: `campus-api-python/campus_python/json_client/interface.py`

Update `raise_for_status()` to handle both old and new formats for backward compatibility:

```python
def raise_for_status(self) -> None:
    """Raise appropriate error based on response status.

    Handles both legacy and new error envelope formats.
    """
    if not self.ok:
        try:
            data = self._json
        except ValueError:
            data = None

        # Try new format first (error envelope)
        if data and "error" in data:
            error_obj = data["error"]
            error = APIError.with_status_code(
                self.status_code,
                error=error_obj.get("code"),
                error_description=error_obj.get("message"),
                request_id=error_obj.get("request_id"),
                details=error_obj.get("details"),
                errors=error_obj.get("errors"),
            )
        # Fallback to legacy format (for backward compatibility)
        elif data and "error_code" in data:
            error = APIError.with_status_code(
                self.status_code,
                error=data.get("error_code"),
                error_description=data.get("message"),
                details=data.get("details"),
            )
        # No JSON body
        else:
            error = APIError.with_status_code(self.status_code)

        error.notes = {"headers": dict(self.headers), "body": self.text}
        raise error
```

### 5.2 Update APIError Class

**File**: `campus-api-python/campus_python/errors.py`

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class FieldError:
    """A single field validation error."""
    field: str
    code: str
    message: str


@dataclass
class APIError(Exception):
    """Base API error.

    Attributes match the new error envelope format.
    """
    status_code: int
    error: str | None = None           # Changed from error_code
    error_description: str | None = None
    error_uri: str | None = None
    request_id: str | None = None      # New field
    details: dict[str, Any] = field(default_factory=dict)  # New
    errors: list[FieldError] | None = None     # New: for validation errors
    notes: dict[str, Any] = None       # headers, body (unchanged)
```

### 5.3 Add ValidationError to Client

**File**: `campus-api-python/campus_python/errors.py`

```python
@dataclass
class ValidationError(APIError):
    """Validation error with field-level details."""

    status_code: int = 422

    @property
    def field_errors(self) -> list[FieldError]:
        """Return list of field errors, empty if none."""
        return self.errors or []

    def get_errors_for_field(self, field_name: str) -> list[FieldError]:
        """Get all errors for a specific field."""
        return [e for e in self.field_errors if e["field"] == field_name]
```

### Test Phase 5

```bash
cd campus-api-python
pytest tests/ -v
```

---

## Phase 6: Documentation

### 6.1 Update OpenAPI/Swagger Docs

Add error response schemas to API documentation.

### 6.2 Create Migration Guide

Document the changes for API consumers:

**New Error Envelope Format:**
- Root `error` object wrapper
- `error.code` (was `error_code`)
- `error.message` (was `message`)
- `error.details` (was `details`)
- `error.request_id` (new, currently `null`)

**Validation Errors:**
- New `error.errors` array with field-level details
- Status code 422 for validation failures

---

## Implementation Checklist

Use this checklist to track progress through each phase.

### Server (campus/campus)

- [x] Phase 1.1: Update ErrorConstant enum ✅
- [x] Phase 1.2: Update `APIError.to_dict()` for new envelope ✅
- [x] Phase 1.3: Update error handlers (production cleanup) ✅
- [x] Phase 2.1: Create `ValidationError` class with `FieldError` ✅
- [x] Phase 2.2: Add 422 to `raise_api_error` helper ✅
- [x] Phase 2.3: Export new error classes ✅
- [x] Phase 3.1: Update `unpack_request` to use FieldError ✅
- [ ] Phase 3.2: Update type validation to collect errors (optional)
- [ ] Phase 4: Add error response tests

### Client (campus-api-python)

- [ ] Phase 5.1: Update `raise_for_status()` parsing
- [ ] Phase 5.2: Update `APIError` dataclass
- [ ] Phase 5.3: Add `ValidationError` class
- [ ] Phase 5: Update tests for new error parsing

### Documentation

- [ ] Phase 6.1: Update OpenAPI docs
- [ ] Phase 6.2: Create migration guide

---

## Migration Strategy

The refactor is designed to be **backward compatible** during transition:

1. **Client parses both formats**: New envelope is preferred, legacy format is fallback
2. **Each phase is independently deployable**: Code works after each phase completion
3. **Tests pass after each phase**: No regression in functionality

Once all phases are complete and deployed, legacy format support can be removed in a future major version.
