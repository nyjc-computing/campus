# Integration Test Refactor Plan

**Status:** In Progress (Phase 1 Complete)
**Created:** 2025-01-30
**Updated:** 2025-01-30
**Context:** Refactoring integration tests to follow coherent testing principles

## Progress Summary

### Completed ✅

**Phase 1: Quick Wins (2025-01-30)**
- ✅ Created `tests/fixtures/tokens.py` with token creation utilities
  - `create_test_token()` - Creates bearer tokens for user context
  - `create_test_client_credentials()` - Creates test clients with Basic Auth
  - `get_basic_auth_headers()` - Helper for Basic Auth headers
  - `get_bearer_auth_headers()` - Helper for Bearer Auth headers
- ✅ Re-enabled `test_assignments.py` with Bearer Auth
  - Removed `@unittest.skip` decorator
  - Updated to use Bearer Auth instead of Basic Auth
  - Fixed route paths to include trailing slashes
- ✅ Added `tests/contract/test_auth_vault.py` with HTTP contract tests
  - 5 tests covering vault endpoint contracts
  - Tests for 401 unauthorized, 404 not found, round-trip, list, delete

### Known Issues 📝

**Phase 1 Limitations:**
- `test_assignments.py` tests 2-12 fail due to pre-existing API bugs:
  - `assignments.py:85` expects `current_user.get('id')` but `current_user` is a User object
  - This is an API implementation bug, not a test issue
- Running multiple test classes in sequence causes storage pollution
  - `reset_test_storage()` between classes doesn't fully isolate
  - Will be addressed in Phase 2 (ServiceManager refactoring)

### Next Steps 🚀

**Phase 2: Test Isolation** (Next Session)
- Eliminate shared ServiceManager pattern
- Each test class gets its own ServiceManager instance
- Add deprecation warnings for `shared=True`

## Executive Summary

This document outlines a comprehensive refactoring strategy for the Campus integration test suite. The current tests have accumulated technical debt through shared state patterns, weak assertions, and incomplete HTTP contract coverage. This plan addresses these issues while maintaining backward compatibility during migration.

## Objectives

1. **Test interfaces, not implementation** - Verify HTTP contracts rather than Flask internals
2. **Test behavioral invariants** - Assert expected HTTP status codes, error formats, auth behavior
3. **Avoid mocks for internal interfaces** - Use real services where possible
4. **Maintain test isolation** - Each test class should be independent, no shared state pollution
5. **Document HTTP contracts explicitly** - Maintain living documentation of API behavior

## Current State Assessment

### What's Working

| Area | Status | Notes |
|------|--------|-------|
| Test backends (SQLite, Memory) | ✅ | [campus.storage.testing](../campus/storage/testing.py) provides in-memory backends |
| ServiceManager pattern | ✅ | Centralized service setup in [tests/fixtures/services.py](../tests/fixtures/services.py) |
| Deployment smoke tests | ✅ | Catch import/config errors |
| TestCampusRequest implementation | ✅ | Path-based routing works correctly |
| Error handler registration | ✅ | Standardized error responses via [campus/common/errors/__init__.py](../campus/common/errors/__init__.py) |

### What Needs Improvement

| Issue | Impact | Priority | Root Cause |
|-------|--------|----------|------------|
| No bearer token test support | [test_assignments.py](../tests/integration/api/test_assignments.py) blocked | P0 | Missing `create_test_token()` fixture |
| Error response format assumptions | Tests use wrong error format | P0 | Plan assumes `error_code` but code returns `error` |
| Shared state in ServiceManager | Tests fail when run in different orders | P1 | `_shared_instance` class variable pattern |
| Global state pollution | `env` module and `_test_apps` registry | P1 | Mutable global state across tests |
| `reset_test_storage()` inconsistency | Unclear when to call vs. fresh ServiceManager | P1 | Both approaches exist without clear guidance |
| Missing HTTP contract documentation | No single source of truth for API behavior | P2 | Contracts scattered across route files |
| Test performance not measured | 2-minute goal has no baseline | P2 | No performance tracking |
| Vault access permissions not tested | ClientAccess.ALL not validated | P2 | Permission system untested |

---

## Critical Gaps Identified

### Gap 1: HTTP Error Contract Misalignment

The original plan's example code assumes an error format that doesn't match implementation.

**Assumed in original plan:**
```python
self.assertEqual(data["error_code"], "UNAUTHORIZED")
```

**Actual vault endpoint** ([campus/auth/routes/vaults.py:66](../campus/auth/routes/vaults.py#L66)):
```python
# Returns simple error dict for 404
return {"error": "Key not found"}, 404
```

**Actual API error format** ([campus/common/errors/api_errors.py](../campus/common/errors/api_errors.py)):
```python
# APIError.to_dict() returns:
{
    "error": "Error message",        # Human-readable message
    "error_code": "UNAUTHORIZED",    # Standardized code constant
    "details": {...},                # Additional context
    "traceback": "..."               # Only in dev/test, removed in production
}
```

**Resolution:** Contract tests must use the actual error format returned by the error handlers. The error handler ([campus/common/errors/__init__.py:53-66](../campus/common/errors/__init__.py#L53-L66)) returns `err.to_dict(), err.status_code`.

### Gap 2: Token Creation Fixture Details Incomplete

The original plan's `create_test_token()` function was incomplete. Here are the corrected implementation details:

**Correct signature from** [campus/auth/resources/credentials.py:160-169](../campus/auth/resources/credentials.py#L160-L169):
```python
def new(
    self,
    *,
    client_id: str,      # Required: from env.CLIENT_ID
    scopes: list[str],   # Required: OAuth scopes like ["read", "write"]
    expiry_seconds: int, # Optional: defaults to campus.config.DEFAULT_TOKEN_EXPIRY_DAYS
) -> campus.model.OAuthToken:
    """Create a new Campus OAuth token."""
    assert self.parent.provider == "campus"  # Only campus provider supported
    token_id = secret.generate_access_token()
    token = campus.model.OAuthToken(
        id=token_id,
        expiry_seconds=expiry_seconds,
        scopes=scopes,
    )
    # Stores in token_storage and cred_storage
```

**Additional requirements:**
1. **Vault access**: Test clients need explicit vault permissions via `ClientAccess`
2. **Storage initialization**: `token_storage` and `cred_storage` must be initialized first
3. **User doesn't need to exist**: The `new()` method creates credentials if they don't exist

### Gap 3: Database Isolation Strategy

The original plan claimed `:memory:` SQLite creates "new empty DB per connection" but the actual implementation uses global resets.

**Actual implementation** ([campus/storage/testing.py:53-60](../campus/storage/testing.py#L53-L60)):
```python
def reset_test_storage():
    """Reset all test storage. Only works in test mode."""
    if is_test_mode():
        from campus.storage.tables.backend.sqlite import SQLiteTable
        from campus.storage.documents.backend.memory import MemoryCollection

        SQLiteTable.reset_database()    # Global reset - affects all connections
        MemoryCollection.reset_storage()  # Global reset - affects all connections
```

**True isolation requires either:**
- Fresh ServiceManager per test class (slower, but truly isolated)
- Transactional rollback (not implemented)
- Explicit `reset_test_storage()` between tests (current approach)

### Gap 4: Missing Auth Contract Coverage

The plan only covered vault endpoints but didn't address:

| Endpoint Group | Routes | Status |
|----------------|--------|--------|
| `/clients` | 11 routes (POST, GET, GET/:id, PATCH, DELETE, POST/revoke, GET/access, etc.) | Not covered |
| `/credentials` | 5 routes (GET, GET/:provider/:user_id, POST, PATCH, DELETE) | Not covered |
| `/sessions` | Multiple routes | Not covered |
| OAuth proxy | Google, GitHub, Discord callbacks | Not covered |

### Gap 5: Authentication Confusion

The plan mixed two authentication methods:

| Auth Type | Usage | Token Source |
|-----------|-------|--------------|
| **Basic Auth** | Service-to-service (client credentials) | `CLIENT_ID:CLIENT_SECRET` from environment |
| **Bearer Auth** | User-context requests | User token from `credentials["campus"][user_id].new()` |

**Critical insight:** The assignments API requires **Bearer Auth** (user context), but [test_assignments.py:14-18](../tests/integration/api/test_assignments.py#L14-L18) uses **Basic Auth** (client context). This is why the test is skipped.

### Gap 6: ClientAccess Permission System

The plan referenced `ClientAccess.ALL` without explaining the permission system.

**From** [campus/model/client.py:42-58](../campus/model/client.py#L42-L58):
```python
@dataclass(eq=False, kw_only=True)
class ClientAccess(Model):
    """Represents access permissions for a client to a vault label."""
    # Bitflag constants
    READ: ClassVar[int] = 1      # 0b0001
    CREATE: ClassVar[int] = 2    # 0b0010
    UPDATE: ClassVar[int] = 4    # 0b0100
    DELETE: ClassVar[int] = 8    # 0b1000
    ALL: ClassVar[int] = 15      # 0b1111 (READ | CREATE | UPDATE | DELETE)
```

**Granting vault access** (from [campus/auth/resources/client.py](../campus/auth/resources/client.py)):
```python
# Via ClientAccessResource.grant()
client_resource[client_id].access.grant(
    vault_label="vault",
    permission=ClientAccess.ALL  # or any combination of flags
)
```

---

## HTTP Contract Reference

### Auth Service Contracts

#### Vault Endpoints (`/auth/v1/vaults/`)

| Method | Path | Auth Required | Success Response | Error Responses |
|--------|------|---------------|------------------|-----------------|
| GET | `/vaults/{label}/` | Basic or Bearer | `{"keys": [...]}, 200` | `401` (no auth), `404` (vault not found) |
| GET | `/vaults/{label}/{key}` | Basic or Bearer | `{"key": value}, 200` | `401`, `{"error": "Key not found"}, 404` |
| POST | `/vaults/{label}/{key}` | Basic or Bearer | `{"key": value}, 200` | `401`, `400` (invalid request) |
| DELETE | `/vaults/{label}/{key}` | Basic or Bearer | `{}, 200` | `401`, `404` |

#### Client Endpoints (`/auth/v1/clients/`)

| Method | Path | Auth Required | Success Response |
|--------|------|---------------|------------------|
| POST | `/clients` | None (creates new) | `{"id": "...", "name": "...", "description": "...", "created_at": "..."}, 200` |
| GET | `/clients` | Basic or Bearer | `{"clients": [...]}, 200` |
| GET | `/clients/{id}` | Basic or Bearer | `{"id": "...", ...}, 200` |
| PATCH | `/clients/{id}` | Basic or Bearer | `{"id": "...", ...}, 200` |
| DELETE | `/clients/{id}` | Basic or Bearer | `{}, 200` |
| POST | `/clients/{id}/revoke` | Basic or Bearer | `{"secret": "..."}, 200` |
| GET | `/clients/{id}/access` | Basic or Bearer | `{"access": [...]}, 200` |
| POST | `/clients/{id}/access/grant` | Basic or Bearer | `{"vault": "...", "permission": N}, 200` |

#### Credentials Endpoints (`/auth/v1/credentials/`)

| Method | Path | Auth Required | Success Response |
|--------|------|---------------|------------------|
| GET | `/credentials/{provider}` | Basic or Bearer | `{"credentials": [...]}, 200` |
| GET | `/credentials/{provider}/{user_id}` | Basic or Bearer | `{"credentials": {...}}, 200` |
| POST | `/credentials/{provider}/{user_id}` | Basic or Bearer | `{"credentials": {...}}, 201` |
| PATCH | `/credentials/{provider}/{user_id}` | Basic or Bearer | `{}, 200` |
| DELETE | `/credentials/{provider}/{user_id}` | Basic or Bearer | `{}, 200` |

### Standard Error Responses

All API errors follow this format ([campus/common/errors/base.py](../campus/common/errors/base.py)):

```python
{
    "error": "Human-readable error message",
    "error_code": "ERROR_CONSTANT",  # From ErrorConstant enum
    "details": {...},                # Optional additional context
    "traceback": "..."               # Only in non-production environments
}
```

**Common error codes:**
- `UNAUTHORIZED` (401): Missing or invalid authentication
- `FORBIDDEN` (403): Authenticated but insufficient permissions
- `INVALID_REQUEST` (400): Malformed request
- `NOT_FOUND` (404): Resource doesn't exist
- `CONFLICT` (409): Resource state conflict (Campus convention for "not found" on updates)
- `SERVER_ERROR` (500): Internal server error

---

## Refactor Strategy

### Phase 1: Quick Wins (1-2 days)

#### 1.1 Create Token Creation Fixture

**File:** [tests/fixtures/tokens.py](../tests/fixtures/tokens.py) (new)

```python
"""tests.fixtures.tokens

Test token creation utilities for integration tests.
"""

from campus.common import env, schema
from campus.auth import resources as auth_resources
from campus.model import ClientAccess


def create_test_token(
    user_id: schema.UserID,
    scopes: list[str] | None = None,
    expiry_seconds: int = 3600,
    grant_vault_access: bool = True
) -> str:
    """Create a test bearer token for integration tests.

    This creates a token directly in the credentials storage,
    bypassing the OAuth flow (which requires Google).

    Args:
        user_id: The user ID to create the token for
        scopes: OAuth scopes to grant (defaults to full access)
        expiry_seconds: Token lifetime in seconds
        grant_vault_access: Whether to grant vault access to the client

    Returns:
        The bearer token string

    Example:
        >>> from tests.fixtures.tokens import create_test_token
        >>> token = create_test_token(schema.UserID("test.user@campus.test"))
        >>> headers = {"Authorization": f"Bearer {token}"}
    """
    from campus.common import devops

    # Ensure we're in test mode
    if env.get("ENV") != devops.TESTING:
        env.ENV = devops.TESTING

    client_id = env.CLIENT_ID

    # Grant vault access to test client (for vault endpoint tests)
    if grant_vault_access:
        try:
            auth_resources.client[client_id].access.grant(
                vault_label="vault",
                permission=ClientAccess.ALL
            )
        except Exception:
            # Client may not have vault access table initialized
            pass

    # Create token via credentials resource
    token = auth_resources.credentials["campus"][user_id].new(
        client_id=client_id,
        scopes=scopes or ["read", "write"],
        expiry_seconds=expiry_seconds
    )

    return token.id


def create_test_client_credentials(
    name: str = "test-client",
    description: str = "Test client for integration tests"
) -> tuple[str, str]:
    """Create a test client with credentials.

    Returns:
        Tuple of (client_id, client_secret)

    Example:
        >>> client_id, secret = create_test_client_credentials()
        >>> headers = {"Authorization": f"Basic {base64.b64encode(f'{client_id}:{secret}').decode()}"}
    """
    import base64

    # Create new client
    client = auth_resources.client.new(name=name, description=description)

    # Generate secret
    secret = auth_resources.client[client.id].revoke()

    return client.id, secret


def get_basic_auth_headers(client_id: str, client_secret: str) -> dict[str, str]:
    """Create Basic Auth headers from credentials.

    Args:
        client_id: The client ID
        client_secret: The client secret

    Returns:
        Headers dict with Authorization header
    """
    import base64

    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


def get_bearer_auth_headers(token: str) -> dict[str, str]:
    """Create Bearer Auth headers from token.

    Args:
        token: The bearer token

    Returns:
        Headers dict with Authorization header
    """
    return {"Authorization": f"Bearer {token}"}
```

#### 1.2 Re-enable test_assignments.py with Bearer Auth

**File:** [tests/integration/api/test_assignments.py](../tests/integration/api/test_assignments.py)

```python
"""Integration tests for campus.assignments API routes."""

import unittest
from campus.common import schema
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestAssignmentsIntegration(unittest.TestCase):
    """Integration tests for the assignments resource in campus.api."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()
        cls.app = cls.service_manager.apps_app

        # Create test user token
        cls.user_id = schema.UserID("test.user@campus.test")
        cls.token = create_test_token(cls.user_id)
        cls.auth_headers = get_bearer_auth_headers(cls.token)

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        """Set up test environment before each test."""
        self.client = self.app.test_client()
        self.app_context = self.app.app_context().push()

    def tearDown(self):
        """Clean up after each test."""
        self.app_context.pop()

    def test_list_assignments_empty(self):
        """GET /assignments should return empty list initially."""
        response = self.client.get('/api/v1/assignments', headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        self.assertEqual(data["data"], [])

    # ... rest of tests with self.auth_headers instead of Basic auth
```

#### 1.3 Add HTTP Contract Tests for Auth Vault

**File:** [tests/contract/test_auth_vault.py](../tests/contract/test_auth_vault.py) (new)

```python
"""HTTP contract tests for campus.auth vault endpoints.

These tests verify the HTTP interface contract for vault operations.
They test status codes, response formats, and authentication behavior.
"""

import unittest
from tests.fixtures import services
from tests.fixtures.tokens import get_basic_auth_headers
from campus.common import env


class TestAuthVaultContract(unittest.TestCase):
    """HTTP contract tests for /auth/v1/vaults/ endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.auth_app

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        self.client = self.app.test_client()
        self.auth_headers = get_basic_auth_headers(env.CLIENT_ID, env.CLIENT_SECRET)

    def test_get_secret_no_auth_returns_401(self):
        """GET /vaults/{label}/{key} without auth returns 401."""
        response = self.client.get("/auth/v1/vaults/vault/SECRET_KEY")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertEqual(data["error_code"], "UNAUTHORIZED")

    def test_get_secret_missing_returns_404(self):
        """GET /vaults/{label}/{key} for missing key returns 404."""
        response = self.client.get(
            "/auth/v1/vaults/vault/MISSING_KEY",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 404)
        data = response.get_json()
        self.assertEqual(data["error"], "Key not found")

    def test_get_set_secret_round_trip(self):
        """SET then GET secret returns the value."""
        # Set a secret
        set_response = self.client.post(
            "/auth/v1/vaults/vault/TEST_KEY",
            json={"value": "test123"},
            headers=self.auth_headers
        )
        self.assertEqual(set_response.status_code, 200)

        # Get it back
        get_response = self.client.get(
            "/auth/v1/vaults/vault/TEST_KEY",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 200)
        data = get_response.get_json()
        self.assertEqual(data["key"], "test123")

    def test_list_vault_keys(self):
        """GET /vaults/{label}/ returns list of keys."""
        # Set up some keys
        self.client.post("/auth/v1/vaults/vault/KEY1", json={"value": "v1"}, headers=self.auth_headers)
        self.client.post("/auth/v1/vaults/vault/KEY2", json={"value": "v2"}, headers=self.auth_headers)

        response = self.client.get("/auth/v1/vaults/vault/", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("keys", data)
        self.assertIn("KEY1", data["keys"])
        self.assertIn("KEY2", data["keys"])

    def test_delete_secret(self):
        """DELETE /vaults/{label}/{key} removes the secret."""
        # Set a secret
        self.client.post("/auth/v1/vaults/vault/DEL_KEY", json={"value": "v"}, headers=self.auth_headers)

        # Delete it
        del_response = self.client.delete(
            "/auth/v1/vaults/vault/DEL_KEY",
            headers=self.auth_headers
        )
        self.assertEqual(del_response.status_code, 200)

        # Verify it's gone
        get_response = self.client.get(
            "/auth/v1/vaults/vault/DEL_KEY",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 404)
```

### Phase 2: Test Isolation (2-3 days)

#### 2.1 Eliminate Shared ServiceManager

**Problem:** `_shared_instance` causes state pollution between test classes.

**Solution:** Each test class gets its own ServiceManager instance.

**File:** [tests/fixtures/services.py](../tests/fixtures/services.py)

```python
# Changes to make:

class ServiceManager:
    # Remove these class variables
    # _shared_instance = None
    # _shared_setup_done = False

    def __init__(self, shared=False):  # Keep shared param temporarily for compatibility
        # ... but deprecate it
        if shared:
            import warnings
            warnings.warn(
                "shared=True is deprecated. Each test should use its own ServiceManager.",
                DeprecationWarning,
                stacklevel=2
            )
        self.auth_app = None
        self.apps_app = None
        self._setup_done = False
        # Remove: self._shared = shared

    def setup(self):
        # Remove shared instance logic
        # ... rest of setup remains the same
        return self

    def close(self):
        # Always clean up, not just for non-shared
        self._cleanup_auth_client()
        # ... rest of cleanup

    # Remove cleanup_shared() classmethod
```

**Trade-off:** Tests run slower (more setup/teardown) but are more reliable.

#### 2.2 Proper Test Database Isolation Strategy

**Two approaches:**

**Option A: Fresh database per test class** (slower, truly isolated)
```python
# In test class setUpClass
import tempfile
import os

class MyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create unique database file for this test class
        cls.db_fd, cls.db_path = tempfile.mkstemp(suffix='.sqlite')

        # Set environment before service setup
        env.TEST_DB_PATH = cls.db_path

        cls.manager = services.create_service_manager()
        cls.manager.setup()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        os.close(cls.db_fd)
        os.unlink(cls.db_path)
```

**Option B: Reset between tests** (faster, shared state)
```python
# Current approach - use reset_test_storage()
import campus.storage.testing

class MyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = services.create_service_manager()
        cls.manager.setup()

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        campus.storage.testing.reset_test_storage()

    def tearDown(self):
        # Optional: reset after each test for more isolation
        campus.storage.testing.reset_test_storage()
        # Re-initialize services
        self.manager.setup()
```

**Recommendation:** Use Option B for now, consider Option A if state pollution issues persist.

### Phase 3: Contract Tests Directory (3-4 days)

#### 3.1 New Directory Structure

```
tests/
├── contract/                    # HTTP contract tests (black-box)
│   ├── __init__.py
│   ├── conftest.py              # Shared pytest fixtures
│   ├── auth/                    # Auth service contracts
│   │   ├── __init__.py
│   │   ├── test_vaults.py       # Vault endpoint contracts
│   │   ├── test_clients.py      # Client management contracts
│   │   └── test_credentials.py  # Credentials endpoint contracts
│   ├── api/                     # API service contracts
│   │   ├── __init__.py
│   │   ├── test_assignments.py  # Assignments API contracts
│   │   └── test_submissions.py  # Submissions API contracts
│   └── fixtures.py              # Contract test fixtures
├── integration/                 # Service integration (gray-box)
│   ├── test_auth_flow.py        # Full OAuth flow tests
│   ├── test_yapper.py           # Event publishing tests
│   └── test_service_integration.py  # Cross-service tests
├── fixtures/                    # Common fixtures (shared)
│   ├── __init__.py
│   ├── services.py              # ServiceManager
│   ├── tokens.py                # Token creation utilities
│   └── storage.py               # Storage test utilities
└── unit/                        # Already exists
```

#### 3.2 Contract Test Fixtures

**File:** [tests/contract/fixtures.py](../tests/contract/fixtures.py) (new)

```python
"""Shared fixtures for HTTP contract tests."""

import pytest
import base64
from campus.common import env


@pytest.fixture
def auth_client():
    """Create a test client with credentials for Basic Auth.

    Yields:
        dict: {client_id, client_secret, auth_headers}
    """
    from campus.auth import resources as auth_resources

    # Create test client
    client = auth_resources.client.new(
        name="contract-test-client",
        description="Client for HTTP contract tests"
    )
    secret = auth_resources.client[client.id].revoke()

    # Grant vault access for vault endpoint tests
    from campus.model import ClientAccess
    try:
        auth_resources.client[client.id].access.grant(
            vault_label="vault",
            permission=ClientAccess.ALL
        )
    except Exception:
        pass  # Vault access may not be initialized

    encoded = base64.b64encode(f'{client.id}:{secret}'.encode()).decode()

    yield {
        "client_id": client.id,
        "client_secret": secret,
        "auth_headers": {"Authorization": f"Basic {encoded}"}
    }

    # Cleanup
    try:
        auth_resources.client[client.id].delete()
    except Exception:
        pass


@pytest.fixture
def user_token(auth_client):
    """Create a test user with bearer token.

    Yields:
        dict: {user_id, token, auth_headers}
    """
    from tests.fixtures.tokens import create_test_token
    from campus.common import schema

    user_id = schema.UserID("contract.test@campus.test")
    token = create_test_token(
        user_id,
        scopes=["read", "write"],
        grant_vault_access=False  # Already granted via auth_client
    )

    yield {
        "user_id": user_id,
        "token": token,
        "auth_headers": {"Authorization": f"Bearer {token}"}
    }


@pytest.fixture
def contract_services(auth_client):
    """Set up services for contract testing.

    This fixture ensures services are initialized once for a test module.
    """
    from tests.fixtures import services

    manager = services.create_service_manager()
    manager.setup()

    yield {
        "auth_app": manager.auth_app,
        "api_app": manager.apps_app,
        "manager": manager
    }

    # Cleanup
    manager.close()
    import campus.storage.testing
    campus.storage.testing.reset_test_storage()
```

#### 3.3 Contract Test Template

```python
"""Contract test template."""

import pytest
from tests.contract.fixtures import contract_services


class TestEndpointContracts:
    """HTTP contract tests for API endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self, contract_services):
        """Set up test client."""
        self.client = contract_services["auth_app"].test_client()
        self.auth_headers = contract_services["auth_headers"]

    def test_endpoint_requires_authentication(self):
        """Request without auth header returns 401."""
        response = self.client.get("/path")
        assert response.status_code == 401
        data = response.get_json()
        assert data["error_code"] == "UNAUTHORIZED"

    def test_endpoint_accepts_valid_auth(self):
        """Valid credentials return success."""
        response = self.client.get("/path", headers=self.auth_headers)
        assert response.status_code == 200

    def test_invalid_request_returns_400(self):
        """Malformed request returns 400."""
        response = self.client.post("/path", json={}, headers=self.auth_headers)
        assert response.status_code == 400
        data = response.get_json()
        assert data["error_code"] == "INVALID_REQUEST"
```

### Phase 4: Migration Path (Ongoing)

#### Migration Steps

1. **Week 1:** Phase 1 (Quick Wins)
   - Create `tests/fixtures/tokens.py`
   - Re-enable `test_assignments.py` with bearer auth
   - Add `tests/contract/test_auth_vault.py`
   - Keep old tests running in parallel

2. **Week 2:** Phase 2 (Test Isolation)
   - Refactor ServiceManager to remove shared mode
   - Add deprecation warnings for `shared=True`
   - Update test classes to use fresh ServiceManager
   - Fix any failing tests due to state changes

3. **Week 3-4:** Phase 3 (Contract Tests)
   - Create `tests/contract/` directory structure
   - Add contract tests for all auth endpoints
   - Add contract tests for API endpoints
   - Document HTTP contracts

4. **Ongoing:** Gradual Migration
   - Add new tests in `tests/contract/`
   - Migrate existing tests to contract style
   - Deprecate old "smoke test" style tests

#### Backward Compatibility

During migration:
- Keep old tests running in `tests/integration/`
- Add new tests in `tests/contract/`
- Mark old tests with `@unittest.skip("Superseded by contract test")` when migrated
- Eventually remove old tests after contract tests prove stable

### Success Criteria

A test suite is considered well-structured when:

1. **Interface-Focused:** Tests verify HTTP contracts (status codes, headers, response formats)
2. **Isolated:** Each test class can run independently in any order
3. **Fast:** Tests complete in under 2 minutes for full suite
4. **Maintainable:** New tests can be added without understanding monkey-patching
5. **Reliable:** Tests don't fail intermittently due to shared state
6. **Documented:** HTTP contracts are explicit and testable

## Open Questions

1. **pytest vs unittest:** Should we migrate to pytest for better fixture support?
   - pytest fixtures are more flexible
   - unittest is already used throughout
   - Migration cost vs. benefit analysis needed

2. **Test containers:** Should we invest in Docker-based contract testing?
   - Pro: Tests real HTTP behavior
   - Con: Slower, more infrastructure
   - Consider for CI/CD pipeline only

3. **Coverage targets:** What percentage of code should contract tests cover?
   - Current: Unknown
   - Target: 80% of HTTP surface area

4. **Client credentials flow:** Should campus.api support OAuth client credentials grant?
   - Would enable service-to-service auth
   - Currently only supports user session tokens (bearer)

## Next Steps

1. **Review this plan** with the team
2. **Create Phase 1 tasks** in issue tracker
3. **Begin implementation:**
   - Create `tests/fixtures/tokens.py`
   - Re-enable `test_assignments.py`
   - Add first contract test file
4. **Measure baseline** test performance
5. **Track progress** against success criteria
