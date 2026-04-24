# Campus Testing Guide

This guide covers testing in Campus: what we test, how tests are organized, and how to run and write tests.

## Critical Reminders

- **Only standard library `unittest`**—no pytest or other test dependencies
- **Use the test runner**: `tests/run_tests.py` handles environment setup automatically
- **Python environment**: pyenv + pipx Poetry + .venv setup (see GETTING-STARTED.md)

## Quick Start

```bash
# Run sanity checks (fast validation, 2-3 seconds)
poetry run python tests/run_tests.py sanity

# Run all unit tests (fast, no external dependencies)
poetry run python tests/run_tests.py unit

# Run all integration tests (requires environment setup)
poetry run python tests/run_tests.py integration

# Run all tests (sanity → type → unit → integration)
poetry run python tests/run_tests.py all

# Run specific test file
poetry run python -m unittest tests.unit.auth.test_resources -v
```

### How `poetry run python` Works

The `poetry run python` command finds the project's virtual environment and runs Python within it. This works consistently across all environments:

| Environment | Command |
|------------|---------|
| Local development | `poetry run python tests/run_tests.py unit` |
| CI/CD | `poetry run python tests/run_tests.py unit` |
| GitHub Codespaces | `poetry run python tests/run_tests.py unit` |

**Why `poetry run`?**
- Works the same everywhere (no environment-specific commands needed)
- Automatically finds the correct Python interpreter
- No need to manually activate venv or remember `.venv/bin/python` paths

## Test Types

### Unit Tests

**Purpose:** Test individual functions and classes in isolation.

- **Location:** `tests/unit/`
- **Dependencies:** None (or mocked)
- **Speed:** Fastest
- **Examples:**
  - Model validation logic
  - Resource CRUD operations
  - Utility functions
  - Schema conversions

**Guidelines:**
- Test only internal logic of each package
- No environment dependencies or cross-package interactions
- Mock external dependencies (may mock `campus.common` classes)
- Must not mock package classes (test real implementations)

### Integration Tests

**Purpose:** Test multiple components working together.

- **Location:** `tests/integration/`
- **Dependencies:** In-memory SQLite, test fixtures
- **Speed:** Medium
- **Examples:**
  - End-to-end API flows
  - Service-to-service communication
  - Database operations
  - State management

**Guidelines:**
- Test package as a whole including DB, API, cross-package interactions
- Use `tests/fixtures/services.py` for environment setup
- Test real implementations with actual dependencies

**Note:** Integration tests use shared state within a test class for performance. Tests that depend on empty state should be named with `test_00_*` prefix to run first.

### Integration Test Base Classes

**NEW:** Integration tests should use base classes from `tests/integration/base.py` to ensure consistent setup/teardown and prevent common bugs.

#### Available Base Classes

##### **`IntegrationTestCase`** (Default)

Use for **most integration tests** that need Flask apps and service manager.

**Provides:**
- ✅ Automatic service manager setup/teardown
- ✅ Storage reset in `setUp()` for per-test isolation
- ✅ Flask app context management
- ✅ Proper cleanup of resources

**Example:**
```python
from tests.integration.base import IntegrationTestCase

class TestMyFeature(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()  # Sets up service_manager
        cls.app = cls.service_manager.apps_app  # Set the Flask app
        # No need to set up client or context - base class handles it

    def test_something(self):
        # self.client and self.app_context are ready to use
        response = self.client.get('/api/v1/endpoint')
        self.assertEqual(response.status_code, 200)
```

**What you DON'T need to write:**
- ❌ `setUpClass`: service manager setup
- ❌ `setUp`: test client and app context
- ❌ `tearDown`: app context cleanup
- ❌ `tearDownClass`: service manager cleanup and storage reset

##### **`IsolatedIntegrationTestCase`**

Use for tests that need **fresh Flask apps** (complete isolation from other test classes).

**When to use:**
- Tests modify Flask app configuration
- Tests use shared state that could conflict
- Tests need complete isolation

**Example:**
```python
from tests.integration.base import IsolatedIntegrationTestCase
from campus.audit.resources.traces import TracesResource

class TestTracing(IsolatedIntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()  # Fresh service manager
        TracesResource.init_storage()  # Initialize storage
        cls.audit_app = cls.manager.audit_app

    def setUp(self):
        super().setUp()  # Resets storage
        TracesResource.init_storage()  # Reinitialize after reset
```

#### Benefits of Base Classes

**Prevents Common Bugs:**
- ❌ Forgetting to reset storage between tests
- ❌ Forgetting to clean up Flask app context
- ❌ Forgetting to close service manager
- ❌ Inconsistent teardown patterns

**Reduces Boilerplate:**
- ✅ Less code to write (50% reduction in setup/teardown)
- ✅ Consistent patterns across all tests
- ✅ Easier to understand test intent
- ✅ Centralized fixes apply to all tests

#### Using Integration Test Base Classes

**Example:**
```python
from tests.integration.base import IntegrationTestCase

class TestMyFeature(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = cls.service_manager.apps_app

    def test_something(self):
        # self.client and self.app_context are ready to use
        response = self.client.get('/api/v1/endpoint')
        self.assertEqual(response.status_code, 200)
```

**What you DON'T need to write:**
- ❌ `setUpClass`: service manager setup
- ❌ `setUp`: test client and app context
- ❌ `tearDown`: app context cleanup
- ❌ `tearDownClass`: service manager cleanup and storage reset

#### Advanced: Combining Base Classes

The `DependencyCheckedTestCase` can be combined with other base classes using multiple inheritance:

```python
class TestMyFeature(IsolatedIntegrationTestCase, DependencyCheckedTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Setup with dependency checking

    @classmethod
    def _check_dependencies(cls):
        # Verify required dependencies
        if not cls._verify_external_service():
            cls._skip_dependency("Service not available. See: #123")
```

### Contract Tests

**Purpose:** Verify HTTP interface contracts.

- **Location:** `tests/contract/`
- **Dependencies:** Flask test client (not real HTTP)
- **Speed:** Fast
- **Examples:**
  - Auth requirements (401 without credentials)
  - Error response formats (409, 400)
  - Response structure validation
  - HTTP status code correctness

See [tests/contract/README.md](../tests/contract/README.md) for specific invariants tested.

### Sanity Tests

**Purpose:** Quick validation tests to catch common issues before running full test suite.

- **Location:** `tests/sanity/`
- **Dependencies:** Minimal (poetry, Python environment)
- **Speed:** Very fast (2-3 seconds)
- **Timeout:** 2 minutes in CI/CD
- **Examples:**
  - Lockfile synchronization (poetry.lock matches pyproject.toml)
  - Python version compatibility
  - Required deployment files exist
  - Module import capability
  - Deployment smoke tests (can modules be configured and started?)

**Guidelines:**
- Test infrastructure setup and configuration
- Verify dependencies are correctly installed
- Check for import failures early
- Validate deployment readiness
- No external service dependencies

**What Makes a Test a "Sanity Test":**

Sanity tests are distinguished by their **scope** and **purpose**:

| Aspect | Sanity Tests | Integration Tests |
|--------|-------------|-------------------|
| **Purpose** | "Can it deploy?" | "Does it work?" |
| **Scope** | Module-level, infrastructure | Service-level, end-to-end |
| **Focus** | Imports, config, startup | Business logic, data flows |
| **Speed** | Very fast (seconds) | Medium (seconds to minutes) |
| **CI/CD Order** | Run FIRST (fail fast) | Run AFTER sanity checks |
| **Examples** | poetry.lock sync, module imports | API endpoints, database operations |

**Current Sanity Tests:**

1. **Infrastructure Tests** (6 tests in `tests/sanity_check.py`):
   - `test_poetry_lock_file_exists` - Verify poetry.lock exists
   - `test_poetry_lock_is_in_sync` - Check poetry.lock matches pyproject.toml
   - `test_poetry_lock_is_valid` - Validate poetry.lock is valid TOML
   - `test_python_version_matches_requirements` - Check Python version compatibility
   - `test_required_files_exist` - Verify critical deployment files present
   - `test_test_fixtures_can_be_imported` - Test fixtures import without errors

2. **Deployment Smoke Tests** (15 tests in `tests/sanity/`):
   - `test_auth_module_can_be_imported` - Verify campus.auth imports
   - `test_auth_app_can_be_created` - Verify auth Flask app creates
   - `test_auth_app_has_secret_key` - Verify auth has SECRET_KEY
   - `test_auth_blueprints_registered` - Verify auth blueprints registered
   - `test_auth_routes_exist` - Verify auth routes exist
   - `test_auth_provider_initialized` - Verify OAuth provider initialized
   - `test_auth_has_error_handlers` - Verify error handlers configured
   - `test_api_module_can_be_imported` - Verify campus.api imports
   - `test_api_app_can_be_created` - Verify API Flask app creates
   - `test_api_app_has_secret_key` - Verify API has SECRET_KEY
   - `test_api_blueprints_registered` - Verify API blueprints registered
   - `test_api_routes_exist` - Verify API routes exist
   - `test_api_has_error_handlers` - Verify error handlers configured
   - `test_wsgi_import` - Verify WSGI entry point works

**When to Add to Sanity Tests:**

Add a test to `tests/sanity/` when:
- ✅ It checks deployment readiness (imports, config, startup)
- ✅ It's very fast (under 1 second)
- ✅ It has no external dependencies (no network, databases)
- ✅ It catches infrastructure issues early
- ✅ It should fail fast in CI/CD before expensive tests

**When NOT to Add to Sanity Tests:**

- ❌ It tests business logic or API behavior → Use unit/integration tests
- ❌ It requires external services or databases → Use integration tests
- ❌ It's slow or resource-intensive → Use integration tests
- ❌ It tests specific functionality → Use unit/integration tests

**Test Organization Philosophy:**

Tests are organized by **when they should run** and **what they verify**:

1. **Sanity tests** (2-3 seconds) → "Can we deploy?"
2. **Unit tests** (60 seconds) → "Do individual components work?"
3. **Integration tests** (5 minutes) → "Do components work together?"
4. **Contract tests** (fast) → "Are HTTP contracts correct?"

This organization ensures:
- Fast feedback on common issues
- Early failure on infrastructure problems
- Efficient use of CI/CD resources
- Clear separation of concerns

## Test Type Decision Tree

```
Are you testing HTTP interface contracts (status codes, auth)?
├── Yes → Contract Test (tests/contract/)
└── No
    Are you testing deployment readiness (imports, config, startup)?
    ├── Yes → Sanity Test (tests/sanity/)
    └── No
        Are you testing cross-service interactions or database operations?
        ├── Yes → Integration Test (tests/integration/)
        └── No → Unit Test (tests/unit/)
```

**Summary:**
- **Sanity tests**: Deployment readiness ("can it deploy?")
- **Contract tests**: HTTP invariants (401 without auth, error formats)
- **Integration tests**: Service-to-service, database operations
- **Unit tests**: Everything else (individual functions, classes)

**Summary:**
- **Contract tests**: HTTP invariants (401 without auth, error formats)
- **Integration tests**: Service-to-service, database operations
- **Unit tests**: Everything else (individual functions, classes)

## Running Tests

### Using the Test Runner (Recommended)

```bash
# All tests
poetry run python tests/run_tests.py all

# Unit tests only
poetry run python tests/run_tests.py unit

# Integration tests only
poetry run python tests/run_tests.py integration

# Sanity checks
poetry run python tests/run_tests.py sanity

# Type checks
poetry run python tests/run_tests.py type

# Package-specific tests
poetry run python tests/run_tests.py unit --module auth
poetry run python tests/run_tests.py unit --module api
```

### Using unittest Directly

```bash
# Run specific test file
poetry run python -m unittest tests.unit.auth.test_resources -v

# Run specific test class
poetry run python -m unittest tests.unit.auth.test_resources.TestAuthResource -v

# Run specific test method
poetry run python -m unittest tests.unit.auth.test_resources.TestAuthResource.test_authenticate -v

# Run all contract tests
poetry run python -m unittest discover -s tests/contract -p "test_*.py"
```

## Test Scope

### What We Test

| Category | Description | Examples |
|----------|-------------|----------|
| **HTTP contracts** | Status codes, response formats, authentication | 401 without auth, 409 for not found, 400 for bad input |
| **Business logic** | CRUD operations, validation, state transitions | Creating assignments, updating circles, token validation |
| **Data flow** | Request → processing → response | Vault get/set, OAuth flow, email OTP delivery |
| **Integration** | Cross-service interactions | Auth + API, API + Yapper, storage + resources |

### What We Don't Test

| Category | Rationale |
|----------|-----------|
| **HTTP layer** | Flask/Werkzeug handles HTTP correctly |
| **Network errors** | Platform responsibility (Railway, Replit, etc.) |
| **Middleware** | WSGI stack is trusted |
| **Flask bugs** | Not our responsibility to test Flask itself |
| **Deployment config** | Covered by manual testing on development environment |
| **Performance** | Out of scope for unit/integration tests |
| **Security auditing** | Out of scope (follow secure coding practices instead) |

### Testing Philosophy

> **We test our code, not our dependencies.**

Our tests verify that Campus API endpoints are implemented correctly. We trust that:
- Flask handles HTTP requests/responses correctly
- The WSGI server (Gunicorn) works as advertised
- The deployment platform (Railway) manages networking

## Test Environment

All tests run in a controlled test environment:

```python
ENV = "testing"          # Test mode enabled
STORAGE_MODE = "1"       # In-memory storage
```

Storage backends in test mode:
- **Tables:** SQLite (`:memory:` or temp file)
- **Documents:** Python dicts
- **Vault:** In-memory storage

## Test Fixtures

Key fixtures in `tests/fixtures/`:

| Fixture | Purpose |
|---------|---------|
| `services.create_service_manager()` | Sets up Flask apps for testing |
| `create_test_token(user_id)` | Creates bearer tokens for authenticated tests |
| `get_basic_auth_headers(id, secret)` | Creates Basic auth headers |
| `get_bearer_auth_headers(token)` | Creates Bearer auth headers |

## Writing New Tests

### Unit Tests

```python
import unittest

class TestMyFeature(unittest.TestCase):
    def test_feature_returns_expected_value(self):
        result = my_feature(input_value)
        self.assertEqual(result, expected_value)
```

### Integration Tests

```python
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers
from tests.integration.base import IntegrationTestCase

class TestMyIntegration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()  # Sets up service_manager
        cls.app = cls.service_manager.apps_app
        cls.token = create_test_token("test@example.com")
        cls.auth_headers = get_bearer_auth_headers(cls.token)
```

### Contract Tests

```python
def test_endpoint_requires_auth(self):
    """GET /endpoint without auth returns 401."""
    response = self.client.get("/api/v1/endpoint")
    assert response.status_code == 401
    data = response.get_json()
    assert data["error_code"] == "UNAUTHORIZED"
```

## Test Isolation Notes

Integration tests use `setUpClass()`/`tearDownClass()` for performance. Data persists between tests in a class.

**Workaround:** Name tests that depend on empty state with `test_00_*` prefix to ensure they run first.

Example:
```python
def test_00_list_is_empty(self):
    """Must run first to verify empty initial state."""
    response = self.client.get("/api/v1/resources")
    assert response.get_json()["data"] == []

def test_create_resource(self):
    """Runs after test_00_list_is_empty."""
    # ... creates a resource
```

## Test Skipping Principles

**Critical Rule:** Tests cannot be skipped unless they can be attributed to a different GitHub issue.

### Why This Rule Exists

Arbitrary test skipping hides real problems and makes the codebase harder to maintain. When tests are skipped without clear attribution:
- We lose confidence in the test suite
- Real issues get masked
- It becomes unclear what needs to be fixed
- Technical debt accumulates unnoticed

### The Pattern

✅ **Correct:** Skip with issue attribution
```python
@unittest.skip("Skipped due to authentication failure in span ingestion. See: https://github.com/nyjc-computing/campus/issues/459")
def test_authorization_header_stripped(self):
    """Test that Authorization header is stripped from stored spans."""
    # ... test code
```

❌ **Wrong:** Skip without attribution
```python
@unittest.skip("Skipping for now")
def test_something(self):
    # ... test code
```

❌ **Wrong:** Skip without filing an issue
```python
@unittest.skip("This test is failing")
def test_something(self):
    # ... test code
```

### Requirements for Skipping Tests

Before skipping a test, you must:

1. **Create or reference a GitHub issue** that documents the problem
2. **Add a skip decorator** with the issue URL in the message
3. **Ensure the fix addresses ALL skipped tests** attributed to that issue

Example:
```python
@unittest.skip("Skipped due to SQLite table creation issue after connection reset. See: https://github.com/nyjc-computing/campus/issues/468")
def test_span_recording(self):
    # Test skipped because issue #468 documents the root cause
    # When #468 is fixed, this test must pass
```

### Fix Attribution

When fixing an issue:
- **All tests skipped for that issue must pass** after the fix
- If a test still fails after the fix, it either:
  - Needs to be re-attributed to a different issue
  - Indicates the fix is incomplete
  - Requires additional investigation

This ensures that issue fixes are complete and verified by the test suite.

### Advanced Pattern: Dependency-Checked Test Classes

When multiple tests in a class depend on the same external dependency (e.g., a service or feature), use **dependency-checked test classes** instead of individual `@unittest.skip` decorators.

#### When to Use This Pattern

Use this pattern when:
- **Multiple tests (3+) in a class are skipped for the same issue**
- Tests require a specific dependency to work (e.g., span ingestion, external service)
- You want a single point of control for all skips

#### The Pattern

Create separate test classes based on dependency requirements:

```python
from tests.integration.base import DependencyCheckedTestCase, IsolatedIntegrationTestCase

# Tests that DON'T require the dependency
class TestMyFeatureBasic(IsolatedIntegrationTestCase):
    """Tests that don't require span ingestion."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Setup without dependency checking

    def test_graceful_degradation(self):
        """Test works even when dependency is unavailable."""
        # Test implementation...
        pass

# Tests that DO require the dependency
class TestMyFeatureWithDependency(IsolatedIntegrationTestCase, DependencyCheckedTestCase):
    """Tests that require functional span ingestion."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # CRITICAL: Verify dependency before running any tests
        cls._check_dependencies()

    @classmethod
    def _check_dependencies(cls) -> None:
        """Verify that required dependencies are available."""
        # Perform dependency check here
        # If check fails, call cls._skip_dependency() with a reason
        if not cls._verify_dependency_works():
            cls._skip_dependency(
                "Dependency not working. "
                "See: https://github.com/user/repo/issues/123"
            )

    # NO individual @unittest.skip decorators needed!
    def test_span_recording(self):
        # Automatically skipped if dependency check fails
        pass

    def test_trace_id_propagation(self):
        # Automatically skipped if dependency check fails
        pass
```

#### Benefits

1. **Single Point of Control**: One dependency check affects entire test class
2. **Clear Skip Reasons**: Test logs show exactly what failed and why
3. **Easy to Fix**: When the issue is resolved, all tests automatically run
4. **Explicit Dependencies**: Test class names indicate what they need
5. **Future-Proof**: New tests added to class automatically get dependency checking

#### Example Implementation

See [tests/integration/test_audit_tracing_middleware.py](../tests/integration/test_audit_tracing_middleware.py) for a complete example of this pattern:

- `TestTracingMiddlewareBasic`: Tests that don't require span ingestion
- `TestTracingMiddlewareSpanIngestion`: Tests that require functional span ingestion (automatically skipped when issue #459 is unresolved)

## Known Gotchas

See [AGENTS.md](../AGENTS.md) for common testing pitfalls:
- Storage initialization order (lazy imports required)
- Flask blueprint registration (shared across test classes)
- Test cleanup requirements
- **Storage re-initialization after reset** (see above)

## External Testing

For tests that require real HTTP or deployment verification:

1. **Development Server:** Set `ENV=development` and test against Railway
2. **Manual Testing:** Use Postman, curl, or browser against development endpoints

These are not automated because they require network access and external services.

## OpenAPI Specification Validation

Campus maintains OpenAPI 3.0.3 specifications for API documentation:

- **Auth Service:** `campus/auth/docs/openapi.yaml`
- **API Service:** `campus/api/docs/openapi.yaml`

### Running Validation

```bash
# Validate auth service spec
poetry run python -m openapi_spec_validator campus/auth/docs/openapi.yaml

# Validate API service spec
poetry run python -m openapi_spec_validator campus/api/docs/openapi.yaml

# Run unit tests (includes OpenAPI validation)
poetry run python tests/run_tests.py unit --module common
```

### OpenAPI Validation Tests

Unit tests in `tests/unit/common/test_openapi_spec.py` automatically validate:
- YAML syntax is valid
- Spec conforms to OpenAPI 3.0.3 schema
- Required top-level fields are present (`info`, `paths`, `components`)

These tests focus on structural validity rather than endpoint-specific details to minimize maintenance as the API evolves.

### Why Validate OpenAPI Specs?

- Ensures API documentation is machine-readable and valid
- Catches syntax errors before deployment
- Enables auto-generation of client SDKs and server stubs
- Supports API mocking and testing tools

## Related Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [development-guidelines.md](development-guidelines.md) - Development practices
- [STYLE-GUIDE.md](STYLE-GUIDE.md) - Code standards
- [tests/contract/README.md](../tests/contract/README.md) - Contract test invariants
