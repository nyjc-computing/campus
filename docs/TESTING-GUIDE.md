# Campus Testing Guide

This guide covers testing in Campus: what we test, how tests are organized, and how to run and write tests.

## Critical Reminders

- **Only standard library `unittest`**—no pytest or other test dependencies
- **Use the test runner**: `tests/run_tests.py` handles environment setup automatically
- **Python environment**: pyenv + pipx Poetry + .venv setup (see GETTING-STARTED.md)

## Quick Start

```bash
# Run all unit tests (fast, no external dependencies)
python tests/run_tests.py unit

# Run all integration tests (requires environment setup)
python tests/run_tests.py integration

# Run all tests
python tests/run_tests.py all

# Run specific test file
python -m unittest tests.unit.auth.test_resources -v
```

**Note:** The test runner automatically detects and uses `.venv/bin/python` when available. If you don't have the venv activated or Poetry in PATH, use the full path:
```bash
.venv/bin/python tests/run_tests.py unit
```

### How `.venv/bin/python` Works

If you're new to Python virtual environments, here's what's happening:

| Command | What It Does | Runs in venv? |
|---------|--------------|---------------|
| `python tests/run_tests.py` | Uses system Python, then auto-detects `.venv` | Yes (via test runner) |
| `.venv/bin/python tests/run_tests.py` | Directly executes the venv's Python | Yes |
| `poetry run python tests/run_tests.py` | Poetry finds venv, runs Python | Yes |
| `source .venv/bin/activate` | Modifies shell to use venv for all commands | Yes (until deactivate) |

**Key insight:** `.venv/bin/python` **IS** the virtual environment's Python interpreter. When you run it directly:
- It uses packages installed in `.venv/lib/python3.11/site-packages/`
- No `activate` step needed
- Same as what `poetry run python` does internally (just faster, no Poetry lookup)

The test runner (`tests/run_tests.py`) checks for `.venv/bin/python` first, then falls back to system Python. This means you can run tests with either:
```bash
# Both work identically in this project
python tests/run_tests.py unit
.venv/bin/python tests/run_tests.py unit
```

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

## Test Type Decision Tree

```
Are you testing HTTP interface contracts (status codes, auth)?
├── Yes → Contract Test (tests/contract/)
└── No
    Are you testing cross-service interactions or database operations?
    ├── Yes → Integration Test (tests/integration/)
    └── No → Unit Test (tests/unit/)
```

**Summary:**
- **Contract tests**: HTTP invariants (401 without auth, error formats)
- **Integration tests**: Service-to-service, database operations
- **Unit tests**: Everything else (individual functions, classes)

## Running Tests

### Using the Test Runner (Recommended)

```bash
# All tests
python tests/run_tests.py all

# Unit tests only
python tests/run_tests.py unit

# Integration tests only
python tests/run_tests.py integration

# Sanity checks
python tests/run_tests.py sanity

# Type checks (requires Poetry for pyright environment)
poetry run python tests/run_tests.py type

# Package-specific tests
python tests/run_tests.py unit --module auth
python tests/run_tests.py unit --module api
```

**Environment notes:**
- Works with activated venv: `source .venv/bin/activate`
- Works with configured PATH (pyenv + pipx)
- **Type checks require `poetry run`** (pyright needs Poetry's environment to find packages)
- Or use Poetry wrapper: `poetry run python tests/run_tests.py unit`

### Using unittest Directly

```bash
# Run specific test file
python -m unittest tests.unit.auth.test_resources -v

# Run specific test class
python -m unittest tests.unit.auth.test_resources.TestAuthResource -v

# Run specific test method
python -m unittest tests.unit.auth.test_resources.TestAuthResource.test_authenticate -v

# Run all contract tests
python -m unittest discover -s tests/contract -p "test_*.py"
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

class TestMyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()
        cls.token = create_test_token("test@example.com")
        cls.auth_headers = get_bearer_auth_headers(cls.token)

    @classmethod
    def tearDownClass(cls):
        cls.service_manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()
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

## Known Gotchas

See [AGENTS.md](../AGENTS.md) for common testing pitfalls:
- Storage initialization order (lazy imports required)
- Flask blueprint registration (shared across test classes)
- Test cleanup requirements

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
python -m openapi_spec_validator campus/auth/docs/openapi.yaml

# Validate API service spec
python -m openapi_spec_validator campus/api/docs/openapi.yaml

# Run unit tests (includes OpenAPI validation)
python tests/run_tests.py unit --module common
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
