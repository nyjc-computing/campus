"""Test error response format compliance with api-error-spec.md"""

import os
import unittest

# Set consistent test environment
os.environ["ENV"] = "development"

from campus.common.errors import (
    ConflictError,
    FieldError,
    ForbiddenError,
    InternalError,
    InvalidRequestError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from campus.common.errors.base import ErrorConstant


class TestErrorEnvelope(unittest.TestCase):
    """All errors must have consistent error envelope structure (Section 3)."""

    def test_invalid_request_error_has_envelope(self):
        """InvalidRequestError must have error.code, error.message, error.request_id."""
        err = InvalidRequestError()
        response = err.to_dict()

        self.assertIn("error", response, "Response must have 'error' key")
        self.assertIn("code", response["error"], "Error must have 'code'")
        self.assertIn("message", response["error"], "Error must have 'message'")
        self.assertIn("request_id", response["error"], "Error must have 'request_id'")
        self.assertIsInstance(response["error"].get("details"), dict, "details must be dict")
        self.assertEqual(err.status_code, 400)

    def test_unauthorized_error_has_envelope(self):
        """UnauthorizedError must have error envelope."""
        err = UnauthorizedError()
        response = err.to_dict()

        self.assertIn("error", response)
        self.assertIn("code", response["error"])
        self.assertEqual(err.status_code, 401)

    def test_forbidden_error_has_envelope(self):
        """ForbiddenError must have error envelope."""
        err = ForbiddenError()
        response = err.to_dict()

        self.assertIn("error", response)
        self.assertEqual(err.status_code, 403)

    def test_not_found_error_has_envelope(self):
        """NotFoundError must have error envelope."""
        err = NotFoundError()
        response = err.to_dict()

        self.assertIn("error", response)
        self.assertEqual(err.status_code, 404)

    def test_conflict_error_has_envelope(self):
        """ConflictError must have error envelope."""
        err = ConflictError()
        response = err.to_dict()

        self.assertIn("error", response)
        self.assertEqual(err.status_code, 409)

    def test_internal_error_has_envelope(self):
        """InternalError must have error envelope."""
        err = InternalError()
        response = err.to_dict()

        self.assertIn("error", response)
        self.assertEqual(err.status_code, 500)

    def test_request_id_is_null(self):
        """request_id is currently always null (not yet implemented)."""
        err = NotFoundError()
        response = err.to_dict()
        self.assertIsNone(response["error"]["request_id"])

    def test_error_with_details(self):
        """Errors can include additional details."""
        err = NotFoundError(
            message="User not found",
            resource_type="User",
            resource_id="123"
        )
        response = err.to_dict()

        self.assertEqual(response["error"]["code"], "NOT_FOUND")
        self.assertEqual(response["error"]["message"], "User not found")
        self.assertEqual(response["error"]["details"]["resource_type"], "User")
        self.assertEqual(response["error"]["details"]["resource_id"], "123")


class TestValidationErrors(unittest.TestCase):
    """Validation errors must include field-level details (Section 5)."""

    def test_validation_error_with_field_errors(self):
        """ValidationError includes errors array."""
        field_errors = [
            FieldError(field="email", code="INVALID_FORMAT", message="Invalid email"),
            FieldError(field="password", code="TOO_SHORT", message="Password too short"),
        ]

        err = ValidationError(errors=field_errors)
        response = err.to_dict()

        self.assertEqual(response["error"]["code"], "VALIDATION_FAILED")
        self.assertIn("errors", response["error"])
        self.assertEqual(len(response["error"]["errors"]), 2)

        for fe in response["error"]["errors"]:
            self.assertIn("field", fe)
            self.assertIn("code", fe)
            self.assertIn("message", fe)

    def test_validation_error_without_field_errors(self):
        """ValidationError without errors still returns valid envelope."""
        err = ValidationError()
        response = err.to_dict()

        self.assertNotIn("errors", response["error"])
        self.assertEqual(response["error"]["code"], "VALIDATION_FAILED")
        self.assertEqual(err.status_code, 422)

    def test_validation_error_custom_message(self):
        """ValidationError can have a custom message."""
        field_errors = [
            FieldError(field="age", code="INVALID_RANGE", message="Must be 18 or older"),
        ]

        err = ValidationError(
            message="Registration failed",
            errors=field_errors
        )
        response = err.to_dict()

        self.assertEqual(response["error"]["message"], "Registration failed")
        self.assertEqual(len(response["error"]["errors"]), 1)


class TestErrorCodes(unittest.TestCase):
    """Error codes must be UPPER_SNAKE_CASE and stable (Section 4)."""

    def test_error_codes_format(self):
        """All error codes should be UPPER_SNAKE_CASE."""
        expected_codes = {
            "CONFLICT",
            "FORBIDDEN",
            "INTERNAL_ERROR",
            "INVALID_REQUEST",
            "NOT_FOUND",
            "UNAUTHORIZED",
            "VALIDATION_FAILED",
        }

        for attr in dir(ErrorConstant):
            if not attr.startswith("_"):
                code = getattr(ErrorConstant, attr)
                self.assertIsInstance(code, str)
                self.assertIn(code, expected_codes, f"Unexpected error code: {code}")

    def test_error_classes_use_correct_codes(self):
        """Each error class should use its designated error code."""
        self.assertEqual(InvalidRequestError().error_code, ErrorConstant.INVALID_REQUEST)
        self.assertEqual(UnauthorizedError().error_code, ErrorConstant.UNAUTHORIZED)
        self.assertEqual(ForbiddenError().error_code, ErrorConstant.FORBIDDEN)
        self.assertEqual(NotFoundError().error_code, ErrorConstant.NOT_FOUND)
        self.assertEqual(ConflictError().error_code, ErrorConstant.CONFLICT)
        self.assertEqual(InternalError().error_code, ErrorConstant.INTERNAL_ERROR)
        self.assertEqual(ValidationError().error_code, ErrorConstant.VALIDATION_FAILED)


class TestEnvironmentSpecificBehavior(unittest.TestCase):
    """Production vs development behavior (Section 6)."""

    def test_development_includes_traceback_for_server_errors(self):
        """Development mode should include traceback in details for 5xx errors."""
        os.environ["ENV"] = "development"
        err = InternalError()
        response = err.to_dict()

        # Traceback should be in details for 500 errors in dev
        self.assertIn("details", response["error"])
        self.assertIn("traceback", response["error"]["details"])

    def test_development_no_traceback_for_client_errors(self):
        """Development mode does not include traceback for 4xx errors."""
        os.environ["ENV"] = "development"
        err = NotFoundError()
        response = err.to_dict()

        # 4xx errors should not have traceback
        details = response["error"].get("details", {})
        self.assertNotIn("traceback", details)
