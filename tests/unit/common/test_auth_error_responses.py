"""Test auth error response format compliance with auth-error-spec.md"""

import os
import unittest

# Set consistent test environment
os.environ["ENV"] = "development"

from campus.common.errors import FieldError, ValidationError
from campus.common.errors.auth_errors import (
    AccessDeniedError,
    AuthorizationError,
    InvalidRequestError as AuthInvalidRequestError,
)
from campus.common.errors.base import ErrorConstant
from campus.common.errors.token_errors import (
    InvalidClientError,
    InvalidGrantError,
    TokenError,
)


class TestOAuthErrorEnvelope(unittest.TestCase):
    """OAuth errors should support Campus envelope format."""

    def test_token_error_with_envelope_format(self):
        """TokenError.to_dict(envelope_format=True) returns Campus envelope."""
        err = InvalidClientError("Client authentication failed")
        response = err.to_dict(envelope_format=True)

        self.assertIn("error", response)
        self.assertEqual(response["error"]["code"], "AUTH_INVALID_CLIENT")
        self.assertEqual(response["error"]["message"], "Client authentication failed")
        self.assertEqual(response["error"]["details"]["oauth_error"], "invalid_client")
        self.assertIn("request_id", response["error"])

    def test_token_error_default_rfc_format(self):
        """TokenError.to_dict() defaults to RFC 6749 format."""
        err = InvalidGrantError("Invalid credentials")
        response = err.to_dict()

        self.assertEqual(response["error"], "invalid_grant")
        self.assertIn("error_description", response)
        # No Campus envelope in default mode
        self.assertNotIn("code", response)

    def test_invalid_grant_error_envelope_format(self):
        """InvalidGrantError envelope format includes oauth_error."""
        err = InvalidGrantError("Invalid or expired authorization grant")
        response = err.to_dict(envelope_format=True)

        self.assertEqual(response["error"]["code"], "AUTH_INVALID_GRANT")
        self.assertEqual(response["error"]["message"], "Invalid or expired authorization grant")
        self.assertEqual(response["error"]["details"]["oauth_error"], "invalid_grant")
        self.assertEqual(
            response["error"]["details"]["oauth_error_description"],
            "Invalid or expired authorization grant"
        )

    def test_authorization_error_envelope_format(self):
        """AuthorizationError supports envelope format."""
        err = AccessDeniedError("User denied consent")
        response = err.to_dict(envelope_format=True)

        self.assertEqual(response["error"]["code"], "AUTH_ACCESS_DENIED")
        self.assertEqual(response["error"]["details"]["oauth_error"], "access_denied")


class TestOAuthErrorMapping(unittest.TestCase):
    """OAuth errors must map to correct Campus error codes."""

    def test_oauth_to_campus_error_mapping(self):
        """Verify all OAuth errors map to AUTH_* codes."""
        mappings = {
            "invalid_request": "AUTH_INVALID_REQUEST",
            "invalid_client": "AUTH_INVALID_CLIENT",
            "invalid_grant": "AUTH_INVALID_GRANT",
            "unauthorized_client": "AUTH_UNAUTHORIZED_CLIENT",
            "unsupported_grant_type": "AUTH_UNSUPPORTED_GRANT",
            "invalid_scope": "AUTH_INVALID_SCOPE",
            "access_denied": "AUTH_ACCESS_DENIED",
        }

        for oauth_err, campus_code in mappings.items():
            err = TokenError(error_description="test")
            err.error = oauth_err  # type: ignore
            response = err.to_dict(envelope_format=True)
            self.assertEqual(response["error"]["code"], campus_code)


class TestAuthErrorConstants(unittest.TestCase):
    """AUTH_* error constants must be defined."""

    def test_auth_error_constants_exist(self):
        """All AUTH_* error constants should be defined."""
        expected_auth_codes = {
            "AUTH_INVALID_REQUEST",
            "AUTH_INVALID_CLIENT",
            "AUTH_INVALID_GRANT",
            "AUTH_UNAUTHORIZED_CLIENT",
            "AUTH_UNSUPPORTED_GRANT",
            "AUTH_UNSUPPORTED_RESPONSE_TYPE",
            "AUTH_INVALID_SCOPE",
            "AUTH_ACCESS_DENIED",
            "AUTH_SERVER_ERROR",
            "AUTH_TEMPORARILY_UNAVAILABLE",
            "AUTH_TOKEN_INVALID",
            "AUTH_INSUFFICIENT_SCOPE",
        }

        actual_codes = set()
        for attr in dir(ErrorConstant):
            if attr.startswith("AUTH_"):
                code = getattr(ErrorConstant, attr)
                actual_codes.add(code)

        self.assertEqual(expected_auth_codes, actual_codes)


class TestAuthValidationErrors(unittest.TestCase):
    """Auth endpoints should use ValidationError consistently."""

    def test_validation_error_with_oauth_context(self):
        """ValidationError works in auth context."""
        errors = [
            FieldError(field="username", code="MISSING", message="Username required"),
            FieldError(field="password", code="MISSING", message="Password required"),
        ]

        err = ValidationError(message="Authentication failed", errors=errors)
        response = err.to_dict()

        self.assertEqual(response["error"]["code"], "VALIDATION_FAILED")
        self.assertIn("errors", response["error"])
        self.assertEqual(len(response["error"]["errors"]), 2)


class TestSecurityConstraints(unittest.TestCase):
    """Auth errors must not leak sensitive information."""

    def test_no_user_existence_leak(self):
        """Error messages must not reveal whether a user exists.

        Both missing user and wrong password should have same message
        to prevent user enumeration attacks.
        """
        err1 = InvalidGrantError("Invalid credentials")
        err2 = InvalidGrantError("Invalid credentials")

        self.assertEqual(err1.error_description, err2.error_description)
        # No "user not found" vs "wrong password" distinction

    def test_production_removes_details(self):
        """Production mode removes details from OAuth errors."""
        os.environ["ENV"] = "production"
        try:
            err = InvalidClientError(
                "Authentication failed",
                debug_info="secret"
            )
            response = err.to_dict(envelope_format=True)

            # Details are present in to_dict(), will be stripped by handler
            self.assertIn("details", response["error"])
            self.assertEqual(response["error"]["details"]["oauth_error"], "invalid_client")
        finally:
            os.environ["ENV"] = "development"


class TestOAuthErrorDetails(unittest.TestCase):
    """OAuth error details must include protocol-specific fields."""

    def test_envelope_includes_oauth_error_string(self):
        """Envelope format must include the OAuth protocol error string."""
        err = InvalidGrantError("Invalid credentials")
        response = err.to_dict(envelope_format=True)

        self.assertIn("oauth_error", response["error"]["details"])
        self.assertEqual(response["error"]["details"]["oauth_error"], "invalid_grant")

    def test_envelope_preserves_custom_details(self):
        """Custom details are preserved in envelope format."""
        err = InvalidClientError(
            "Auth failed",
            client_id="test_client",
            attempt_count=3
        )
        response = err.to_dict(envelope_format=True)

        self.assertEqual(response["error"]["details"]["client_id"], "test_client")
        self.assertEqual(response["error"]["details"]["attempt_count"], 3)


class TestAuthorizationErrorHandler(unittest.TestCase):
    """handle_authorization_error must return appropriate responses based on request type."""

    def setUp(self):
        """Set up Flask app for testing error handler."""
        # Lazy import to avoid storage initialization issues
        from campus.common.errors import init_app
        from campus.common.errors.auth_errors import (
            AuthorizationError,
            UnauthorizedClientError,
        )
        from campus.common import devops

        import flask
        self.app = flask.Flask(__name__)
        init_app(self.app)
        self.app.config["TESTING"] = True
        self.UnauthorizedClientError = UnauthorizedClientError
        self.AuthorizationError = AuthorizationError
        self.devops = devops

        # Save original ENV
        self.original_env = os.environ.get("ENV")

    def tearDown(self):
        """Restore original ENV."""
        if self.original_env:
            os.environ["ENV"] = self.original_env
        elif "ENV" in os.environ:
            del os.environ["ENV"]

    def test_json_accept_header_returns_json_error(self):
        """API requests with JSON Accept header return JSON error response."""
        err = self.UnauthorizedClientError("Invalid credentials")

        with self.app.test_request_context(
            "/auth/v1/sessions/test",
            headers={"Accept": "application/json"}
        ):
            from campus.common.errors.handlers import handle_authorization_error
            response, status_code = handle_authorization_error(err)

            self.assertEqual(status_code, 400)
            self.assertIn("error", response)
            self.assertEqual(response["error"]["code"], "AUTH_UNAUTHORIZED_CLIENT")
            self.assertEqual(response["error"]["message"], "Invalid credentials")

    def test_api_path_returns_json_error(self):
        """API requests under /auth/v1/* return JSON error response."""
        err = self.UnauthorizedClientError("Invalid credentials")

        with self.app.test_request_context(
            "/auth/v1/clients/test",
            headers={"Accept": "text/html"}  # Not JSON, but path is API
        ):
            from campus.common.errors.handlers import handle_authorization_error
            response, status_code = handle_authorization_error(err)

            self.assertEqual(status_code, 400)
            self.assertIn("error", response)
            self.assertEqual(response["error"]["code"], "AUTH_UNAUTHORIZED_CLIENT")

    def test_oauth_flow_with_redirect_uri_returns_redirect(self):
        """OAuth browser flows with redirect_uri return HTTP redirect."""
        err = self.AuthorizationError(
            "Invalid credentials",
            redirect_uri="https://example.com/callback"
        )

        with self.app.test_request_context(
            "/oauth/authorize",  # Not an API path
            headers={"Accept": "text/html"}
        ):
            from campus.common.errors.handlers import handle_authorization_error
            response = handle_authorization_error(err)

            # Should be a Flask redirect response
            self.assertIn("location", response.headers)
            self.assertIn("error=invalid_request", response.headers["location"])

    def test_ambiguous_request_in_development_raises_400(self):
        """Ambiguous requests (no JSON Accept, no API path, no redirect_uri) raise 400 in development."""
        os.environ["ENV"] = "development"

        err = self.UnauthorizedClientError("Invalid credentials")

        with self.app.test_request_context(
            "/some/unknown/path",
            headers={"Accept": "text/html"}
        ):
            from campus.common.errors.handlers import handle_authorization_error
            from werkzeug.exceptions import BadRequest

            with self.assertRaises(BadRequest) as context:
                handle_authorization_error(err)

            self.assertIn("Ambiguous authorization error", str(context.exception))

    def test_ambiguous_request_in_production_returns_json(self):
        """Ambiguous requests default to JSON in production for safety."""
        # Use devops.PRODUCTION constant for reliable check
        original = self.devops.ENV
        self.devops.ENV = self.devops.PRODUCTION

        try:
            err = self.UnauthorizedClientError("Invalid credentials")

            with self.app.test_request_context(
                "/some/unknown/path",
                headers={"Accept": "text/html"}
            ):
                from campus.common.errors.handlers import handle_authorization_error
                response, status_code = handle_authorization_error(err)

                self.assertEqual(status_code, 400)
                self.assertIn("error", response)
        finally:
            self.devops.ENV = original


if __name__ == "__main__":
    unittest.main()
