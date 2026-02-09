# Auth Error Specification Refactor Plan

This document outlines the phased implementation plan to bring the Campus Auth error handling into compliance with [auth-error-spec.md](./auth-error-spec.md).

**Each phase results in working code that passes all existing tests.** New tests for error-spec compliance are added at the appropriate phases.

---

## Progress Summary

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | Pending | Core error structure (OAuth error envelope) |
| 2 | Pending | Validation error structure |
| 3 | Pending | Update validation code (including type validation) |
| 4 | Pending | Add error response tests |
| 5 | Pending | Client-side updates (campus-api-python) |
| 6 | Pending | Documentation (OpenAPI spec) |

---

## Phase 1: Core Error Structure (Server) ⏸️

**Goal**: Update OAuth error classes to use the new Campus error envelope format while maintaining RFC 6749 compliance.

### Key Differences from API Errors

OAuth errors have **dual representation**:
1. Canonical Campus error code (`error.code`) - internal, stable
2. OAuth protocol error string (`details.oauth_error`) - RFC-defined

### 1.1 Update OAuthError Base Class

**File**: `campus/common/errors/base.py`

The existing `OAuthError.to_dict()` returns RFC 6749 format only. It needs to also support the Campus envelope for non-redirect endpoints.

Current (RFC 6749 only):
```python
def to_dict(self) -> dict[str, Any]:
    err_obj = {
        "error": self.error,
        "error_description": self.error_description,
        "error_uri": self.error_uri,
        "details": self.details,
    }
    return err_obj
```

New (dual format support):
```python
def to_dict(self, envelope_format: bool = False) -> dict[str, Any]:
    """Convert to dict.

    Args:
        envelope_format: If True, use Campus error envelope.
                       If False, use RFC 6749 format (default for OAuth).

    Returns:
        RFC 6749 format by default, Campus envelope when requested.
    """
    if envelope_format:
        # Campus envelope for API consistency
        return {
            "error": {
                "code": f"AUTH_{self.error.upper()}",
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
    return {
        "error": self.error,
        "error_description": self.error_description,
        "error_uri": self.error_uri,
        "details": self.details,
    }
```

### 1.2 Add Auth-Specific Error Constants

**File**: `campus/common/errors/base.py`

Add to `ErrorConstant` enum:
```python
# OAuth/Auth errors
AUTH_INVALID_REQUEST = "AUTH_INVALID_REQUEST"
AUTH_INVALID_CLIENT = "AUTH_INVALID_CLIENT"
AUTH_INVALID_GRANT = "AUTH_INVALID_GRANT"
AUTH_UNAUTHORIZED_CLIENT = "AUTH_UNAUTHORIZED_CLIENT"
AUTH_UNSUPPORTED_GRANT = "AUTH_UNSUPPORTED_GRANT"
AUTH_INVALID_SCOPE = "AUTH_INVALID_SCOPE"
AUTH_ACCESS_DENIED = "AUTH_ACCESS_DENIED"
AUTH_SERVER_ERROR = "AUTH_SERVER_ERROR"
AUTH_TEMPORARILY_UNAVAILABLE = "AUTH_TEMPORARILY_UNAVAILABLE"
AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
AUTH_INSUFFICIENT_SCOPE = "AUTH_INSUFFICIENT_SCOPE"
```

### 1.3 Update Error Handlers

**File**: `campus/common/errors/__init__.py`

Update `handle_token_error()` to optionally return envelope format:
```python
def handle_token_error(
        err: token_errors.TokenError
) -> tuple[JsonDict, int]:
    """Handle OAuth token request errors.

    Returns Campus error envelope with OAuth details.
    """
    module = get_caller()
    logger.exception("TokenError in %s: %s", module, err)
    err_dict = err.to_dict(envelope_format=True)
    from campus.common import devops
    if devops.ENV == devops.PRODUCTION:
        err_dict["error"].pop("details", None)
    return err_dict, err.status_code
```

**Note**: `handle_authorization_error()` must continue using redirects (RFC 6749 requirement). No envelope format for authorization endpoint.

### Test Phase 1

```bash
cd campus
poetry run python -m unittest discover tests/unit -k auth
poetry run python -m unittest discover tests/integration -k auth
```

---

## Phase 2: Validation Error Structure ✅ (Already Complete)

**Status**: The validation error structure from API errors can be reused.

### 2.1 Reuse Existing ValidationError

**File**: `campus/common/errors/validation.py`

This file already exists from the API error refactoring:
- `FieldError` TypedDict
- `ValidationError` class with status code 422
- Support for field-level errors array

No changes needed - this module is shared across campus.api and campus.auth.

### 2.2 Export from Auth Module

**File**: `campus/auth/__init__.py` (if needed)

Ensure ValidationError is accessible for auth endpoints.

---

## Phase 3: Update Validation Code ⏸️

**Goal**: Convert existing validation errors in auth endpoints to use structured format, including type validation.

### 3.1 Identify Auth Validation Points

Auth endpoints that need validation:

| Endpoint | Validation Needed |
|----------|-------------------|
| `/token` | grant_type, username, password, scope |
| `/authorize` | response_type, client_id, redirect_uri, scope |
| `/clients` | client metadata validation |
| `/users` | user creation fields |
| `/logins` | email, password fields |

### 3.2 Update `unpack_into` for Auth (Already Done)

**File**: `campus/flask_campus/utils.py`

The `unpack_into` function already raises `ValidationError` with structured `FieldError` array. This is used by both API and Auth.

### 3.3 Update Type Validation ⏸️ (NEW - This Time!)

**File**: `campus/common/validation/record.py`

Enhance type validation to return `FieldError` objects instead of raising directly:

```python
def validate_types(
        value: dict[str, Any],
        schema: dict[str, type],
        *,
        ignore_extra: bool = False
) -> list[FieldError]:
    """Validate value types against schema.

    Returns list of FieldError instead of raising.
    """
    from campus.common.errors import FieldError
    errors: list[FieldError] = []

    for key, expected_type in schema.items():
        if key not in value:
            continue

        actual_value = value[key]
        if not isinstance(actual_value, expected_type):
            errors.append(FieldError(
                field=key,
                code="INVALID_TYPE",
                message=f"Expected {expected_type.__name__}, got {type(actual_value).__name__}"
            ))

    return errors
```

### 3.4 Update Auth Resources to Collect Errors

Example for `/token` endpoint validation:

```python
def validate_token_request(data: dict[str, Any]) -> None:
    """Validate token request and raise ValidationError with all field errors."""
    from campus.common.errors import ValidationError, FieldError

    errors: list[FieldError] = []

    # Check grant_type
    if "grant_type" not in data:
        errors.append(FieldError(
            field="grant_type",
            code="MISSING",
            message="Missing required field: grant_type"
        ))
    elif data["grant_type"] not in {"authorization_code", "password", "client_credentials", "refresh_token"}:
        errors.append(FieldError(
            field="grant_type",
            code="INVALID_VALUE",
            message=f"Invalid grant_type: {data['grant_type']}"
        ))

    # Check username for password grant
    if data.get("grant_type") == "password":
        if not data.get("username"):
            errors.append(FieldError(
                field="username",
                code="MISSING",
                message="username is required for password grant"
            ))
        if not data.get("password"):
            errors.append(FieldError(
                field="password",
                code="MISSING",
                message="password is required for password grant"
            ))

    if errors:
        raise ValidationError(
            message="Token request validation failed",
            errors=errors
        )
```

### Test Phase 3

```bash
cd campus
poetry run python tests/run_tests.py all
```

---

## Phase 4: Add Error Response Tests ⏸️

**Goal**: Ensure auth error responses are spec-compliant.

### 4.1 Create Auth Error Response Test Module

**New file**: `campus/tests/auth/test_error_responses.py`

```python
"""Test auth error response format compliance with auth-error-spec.md"""

import unittest
import os

os.environ["ENV"] = "development"

from campus.common.errors import (
    ValidationError,
    FieldError,
)
from campus.common.errors.auth_errors import (
    AccessDeniedError,
    AuthorizationError,
    InvalidRequestError as AuthInvalidRequestError,
)
from campus.common.errors.token_errors import (
    InvalidClientError,
    InvalidGrantError,
    TokenError,
)


class TestOAuthErrorEnvelope:
    """OAuth errors should support Campus envelope format."""

    def test_token_error_with_envelope_format(self):
        """TokenError.to_dict(envelope_format=True) returns Campus envelope."""
        err = InvalidClientError("Client authentication failed")
        response = err.to_dict(envelope_format=True)

        assert "error" in response
        assert response["error"]["code"] == "AUTH_INVALID_CLIENT"
        assert response["error"]["message"] == "Client authentication failed"
        assert response["error"]["details"]["oauth_error"] == "invalid_client"
        assert "request_id" in response["error"]

    def test_token_error_default_rfc_format(self):
        """TokenError.to_dict() defaults to RFC 6749 format."""
        err = InvalidGrantError("Invalid credentials")
        response = err.to_dict()

        assert response["error"] == "invalid_grant"
        assert "error_description" in response
        # No Campus envelope in default mode
        assert "code" not in response


class TestOAuthErrorMapping:
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
            assert response["error"]["code"] == campus_code


class TestAuthValidationErrors:
    """Auth endpoints should use ValidationError consistently."""

    def test_validation_error_with_oauth_context(self):
        """ValidationError works in auth context."""
        errors = [
            FieldError(field="username", code="MISSING", message="Username required"),
            FieldError(field="password", code="MISSING", message="Password required"),
        ]

        err = ValidationError(message="Authentication failed", errors=errors)
        response = err.to_dict()

        assert response["error"]["code"] == "VALIDATION_FAILED"
        assert "errors" in response["error"]
        assert len(response["error"]["errors"]) == 2


class TestSecurityConstraints:
    """Auth errors must not leak sensitive information."""

    def test_no_user_existence_leak(self):
        """Error messages must not reveal whether a user exists."""
        # Both missing user and wrong password should have same message
        err1 = InvalidGrantError("Invalid credentials")
        err2 = InvalidGrantError("Invalid credentials")

        assert err1.error_description == err2.error_description
        # No "user not found" vs "wrong password" distinction

    def test_production_removes_details(self):
        """Production mode removes details from OAuth errors."""
        os.environ["ENV"] = "production"
        err = InvalidClientError("Authentication failed", debug_info="secret")
        response = err.to_dict(envelope_format=True)

        # Details should be stripped by handler, not in to_dict
        # Handler behavior is tested in integration tests


if __name__ == "__main__":
    unittest.main()
```

### Test Phase 4

```bash
cd campus
poetry run python -m unittest tests.auth.test_error_responses -v
```

---

## Phase 5: Client-Side Updates (campus-api-python) ⏸️

**Goal**: Update Python client to handle auth error responses with OAuth details.

### 5.1 Update Error Parsing for OAuth Errors

**File**: `campus-api-python/campus_python/errors.py`

Add OAuth-specific error parsing:

```python
class OAuthError(APIError):
    """Base error for OAuth/token endpoint responses."""

    @property
    def oauth_error(self) -> str | None:
        """Get the OAuth protocol error string."""
        return self.details.get("oauth_error") if self.details else None

    @property
    def oauth_error_description(self) -> str | None:
        """Get the OAuth error description."""
        return self.details.get("oauth_error_description") if self.details else None


class AuthenticationError(OAuthError):
    """Raised when authentication fails."""
    status_code = 401
    error = "AUTH_TOKEN_INVALID"


class InsufficientScopeError(OAuthError):
    """Raised when token lacks required scope."""
    status_code = 403
    error = "AUTH_INSUFFICIENT_SCOPE"
```

### 5.2 Update `with_status_code` for OAuth Details

**File**: `campus-api-python/campus_python/errors.py`

Update parsing to extract `oauth_error` from details:

```python
# In with_status_code method, after parsing response_data
if isinstance(response_data, dict) and "error" in response_data:
    error_obj = response_data["error"]
    # ... existing code ...

    # Extract OAuth-specific details
    if "details" in error_obj and isinstance(error_obj["details"], dict):
        oauth_error = error_obj["details"].get("oauth_error")
        if oauth_error:
            details = details or {}
            details["oauth_error"] = oauth_error
            details["oauth_error_description"] = error_obj["details"].get(
                "oauth_error_description"
            )
```

### Test Phase 5

```bash
cd campus-api-python
python -m pytest tests/unit/test_errors.py -v
```

---

## Phase 6: Documentation (OpenAPI Spec) ⏸️

**Goal**: Create OpenAPI spec for auth endpoints with error response schemas.

### 6.1 Create Auth OpenAPI Spec

**New file**: `campus/auth/docs/openapi.yaml`

```yaml
openapi: 3.0.3
info:
  title: Campus Auth API
  description: |
    Campus OAuth 2.0 Authorization Server and Authentication API.

    ## Error Responses

    All errors follow the Campus error envelope format while maintaining
    OAuth 2.0 compliance (RFC 6749).

    OAuth-specific details are included in the `details.oauth_error` field.
  version: 0.1.0

servers:
  - url: https://auth.campus.nyjc.app
    description: Production
  - url: https://auth.campus.nyjc.dev
    description: Staging
  - url: https://campusauth-development.up.railway.app
    description: Development

components:
  schemas:
    # Reuse API error schemas where applicable
    ErrorEnvelope:
      type: object
      required: [error]
      properties:
        error:
          $ref: '#/components/schemas/AuthError'

    AuthError:
      type: object
      required: [code, message, request_id]
      properties:
        code:
          type: string
          description: Campus error code (AUTH_* prefix)
          example: AUTH_INVALID_CLIENT
        message:
          type: string
          description: Human-readable error message
        request_id:
          type: string
          nullable: true
        details:
          type: object
          properties:
            oauth_error:
              type: string
              description: RFC 6749 OAuth error string
              example: invalid_client
            oauth_error_description:
              type: string
              description: OAuth error description
            required_scopes:
              type: array
              items:
                type: string
              description: Required scopes for insufficient_scope errors

    # OAuth-specific error responses (RFC 6749 format)
    OAuthTokenErrorResponse:
      type: object
      required: [error]
      properties:
        error:
          type: string
          enum:
            - invalid_request
            - invalid_client
            - invalid_grant
            - unauthorized_client
            - unsupported_grant_type
            - invalid_scope
        error_description:
          type: string
        error_uri:
          type: string
          format: uri

  responses:
    InvalidClient:
      description: Client authentication failed (401)
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorEnvelope'
          example:
            error:
              code: AUTH_INVALID_CLIENT
              message: Client authentication failed
              request_id: null
              details:
                oauth_error: invalid_client

    InvalidGrant:
      description: Invalid or expired authorization grant (400)
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ErrorEnvelope'
          example:
            error:
              code: AUTH_INVALID_GRANT
              message: Invalid credentials
              request_id: null
              details:
                oauth_error: invalid_grant

paths:
  /oauth/token:
    post:
      summary: Request token
      description: Get an access token using OAuth 2.0 grant
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [grant_type]
              properties:
                grant_type:
                  type: string
                  enum: [authorization_code, password, client_credentials, refresh_token]
                username:
                  type: string
                password:
                  type: string
                refresh_token:
                  type: string
      responses:
        '200':
          description: Token granted successfully
        '400':
          $ref: '#/components/responses/InvalidGrant'
        '401':
          $ref: '#/components/responses/InvalidClient'
```

### Test Phase 6

```bash
# Validate OpenAPI spec
npx @apidevtools/swagger-cli validate campus/auth/docs/openapi.yaml
```

---

## Implementation Checklist

### Server (campus/campus)

- [ ] Phase 1.1: Update OAuthError.to_dict() with envelope_format parameter
- [ ] Phase 1.2: Add AUTH_* error constants to ErrorConstant enum
- [ ] Phase 1.3: Update handle_token_error() for envelope format
- [ ] Phase 2: Reuse existing ValidationError/FieldError (already done)
- [ ] Phase 3.1: Identify all auth validation points
- [ ] Phase 3.2: Update type validation to collect errors (NEW)
- [ ] Phase 3.3: Update auth resources to use ValidationError
- [ ] Phase 4: Add auth error response tests
- [ ] Phase 5: Update campus-api-python auth error parsing
- [ ] Phase 6: Create auth OpenAPI spec

### Key Differences from API Errors

| Aspect | API Errors | Auth Errors |
|--------|------------|-------------|
| Format | Single error envelope | Dual: Campus envelope + RFC 6749 |
| Error codes | NOT_FOUND, etc. | AUTH_INVALID_CLIENT, etc. |
| Protocol | REST only | OAuth 2.0 (RFC 6749) |
| Redirects | None | /authorize uses redirects |
| Details | General metadata | Must include oauth_error field |

---

## Notes

1. **OAuth Compliance**: All changes must maintain RFC 6749 compliance
2. **Redirect Handling**: /authorize endpoint continues using redirects (no JSON errors)
3. **Shared Modules**: ValidationError, FieldError reused from API errors
4. **Type Validation**: This time we'll implement the full type validation enhancement
