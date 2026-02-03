# Campus Test Plan

This document defines what we test, what we don't test, and how tests are organized.

## Scope

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

## Test Organization

```
tests/
├── unit/                    # Unit tests (fast, isolated)
│   ├── auth/                # Auth service unit tests
│   ├── api/                 # API service unit tests
│   ├── storage/             # Storage layer unit tests
│   ├── yapper/              # Yapper unit tests
│   └── common/              # Shared utilities tests
│
├── integration/             # Integration tests (slower, cross-service)
│   ├── auth/                # Auth service integration
│   ├── api/                 # API service integration
│   └── yapper/              # Yapper integration
│
├── contract/                # HTTP contract tests (interface invariants)
│   ├── test_auth_vault.py   # Vault endpoint contracts
│   ├── test_auth_clients.py # Client CRUD contracts
│   ├── test_auth_*.py       # Other auth contracts
│   └── test_api_*.py        # API endpoint contracts
│
├── fixtures/                # Shared test fixtures
│   ├── services.py          # ServiceManager for test coordination
│   ├── tokens.py            # Test token creation utilities
│   └── auth.py              # Auth service initialization
│
└── flask_test/              # Flask test client adapters
    ├── campus_request.py    # Test-compatible CampusRequest
    ├── client.py            # FlaskTestClient wrapper
    └── response.py          # FlaskTestResponse adapter
```

See [tests/README.md](../tests/README.md) for detailed test documentation.

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

See [tests/contract/README.md](../tests/contract/README.md) for invariants tested.

## Running Tests

```bash
# Run all unit tests (fast, no external dependencies)
poetry run python tests/run_tests.py unit

# Run all integration tests (requires environment setup)
poetry run python tests/run_tests.py integration

# Run all contract tests (HTTP interface invariants)
poetry run python -m unittest discover -s tests/contract -p "test_*.py"

# Run all tests
poetry run python tests/run_tests.py all

# Run specific test file
poetry run python -m unittest tests.contract.test_auth_vault -v

# Run specific test module
poetry run python tests/run_tests.py unit --module auth
```

## Test Fixtures

Key fixtures in `tests/fixtures/`:

| Fixture | Purpose |
|---------|---------|
| `services.create_service_manager()` | Sets up Flask apps for testing |
| `create_test_token(user_id)` | Creates bearer tokens for authenticated tests |
| `get_basic_auth_headers(id, secret)` | Creates Basic auth headers |
| `get_bearer_auth_headers(token)` | Creates Bearer auth headers |

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

## External Testing

For tests that require real HTTP or deployment verification:

1. **Development Server:** Set `ENV=development` and test against Railway
2. **Manual Testing:** Use Postman, curl, or browser against development endpoints

These are not automated because they require network access and external services.

## Related Documentation

- [tests/README.md](../tests/README.md) - Detailed test directory documentation
- [tests/contract/README.md](../tests/contract/README.md) - Contract test invariants
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [development-guidelines.md](development-guidelines.md) - Development practices
