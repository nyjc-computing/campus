# Integration Test Refactor Analysis

**Date:** 2025-01-30 (Updated 2025-02-03)
**Context:** Review of integration test infrastructure after fixing failing tests

**Status:** ✅ Complete - See [test-plan.md](test-plan.md) for current test strategy

## Summary of Completed Work

All "Quick Wins" and "Medium Term" items from this analysis have been completed:

- ✅ HTTP contract tests for auth vault endpoints
- ✅ Error response format tests (401, 409, 400)
- ✅ `auth.init()` and `yapper.init()` are idempotent
- ✅ Token creation fixture for bearer token tests (`tests/fixtures/tokens.py`)
- ✅ `test_assignments.py` re-enabled with bearer auth
- ✅ Contract tests for API endpoints (`tests/contract/test_api_*.py`)
- ✅ Contract test documentation (`tests/contract/README.md`)
- ✅ Test plan documentation (`docs/test-plan.md`)

**Decision on External Dependencies (#3):** The Flask test client approach is appropriate for our scope. We test our API implementation, not the HTTP layer or deployment platform. See [test-plan.md](test-plan.md) for detailed scope.

**Remaining Open Questions:** Tracked as GitHub issues #334-#337

## Summary of Issues Encountered

### 1. Monkey-Patching Complexity
- **Problem:** Tests rely on monkey-patching `campus_python.CampusRequest` with a `TestCampusRequest` class
- **Impact:** Complex test setup, fragile to external library changes
- **Symptom:** `patch_campus_python()` must be called before any `Campus` instances are created
- **Fragility:** Import order matters - campus-python caches `CampusRequest` at import time

### 2. Shared State Between Test Classes
- **Problem:** `ServiceManager` uses shared instances (`_shared_instance`) across test classes
- **Impact:** State pollution when `reset_test_storage()` is called
- **Fix Required:** Had to make `auth.init()` and `yapper.init()` idempotent
- **Ongoing:** Blueprints still have issues with re-registration

### 3. Storage Backend State Management
- **Problem:** SQLite in-memory database (`:memory:`) creates new empty DB on each connection
- **Impact:** Yapper tests initially failed because each connection saw empty database
- **Fix:** Changed to file-based SQLite with `tempfile.mkstemp()`
- **Open Question:** Should the storage backend handle this transparently?

### 4. Type Annotation Issues with Lazy Initialization
- **Problem:** `yapper: YapperInterface | None = None` caused pyright errors
- **Root Cause:** Type checker doesn't know `init_app()` is always called before use
- **Fix:** Used `# type: ignore` and removed `| None` from annotations
- **Debt:** This sacrifices type safety for test convenience

### 5. Authentication Strategy Confusion
- **Problem:** `test_assignments.py` used Basic auth (client credentials) but API expects Bearer tokens (user sessions)
- **Root Cause:** No client_credentials grant flow implemented in campus.auth
- **Workaround:** Skipped tests with TODO comment
- **Architectural Question:** Should API support service-to-service auth via client credentials?

### 6. ENV Value Mismatch
- **Problem:** campus-api-python didn't support `ENV="testing"` initially
- **Impact:** Tests failed with "Invalid ENV value" when wsgi tried to create Campus client
- **Fix:** Added "testing" case to campus-api-python (requires coordination between repos)

### 7. Flask Blueprint Re-registration
- **Problem:** `before_request()` can't be added to blueprint after it's been registered
- **Impact:** `test_wsgi` fails when `init_app()` called multiple times
- **Status:** Skipped with TODO - fundamental Flask limitation

## Current Test Structure Analysis

### Test Categories

| Category | Files | Purpose | Quality Assessment |
|----------|-------|---------|-------------------|
| **Deployment Smoke Tests** | `test_auth_deployment.py`, `test_api_deployment.py` | Verify modules can be imported and apps created | ✅ Good - tests deployability, not functionality |
| **Auth Routes Tests** | `test_auth_routes.py` | Vault API endpoints work | ⚠️ Limited - mostly checks response is parseable |
| **Yapper Tests** | `test_yapper.py` | Message broker functionality | ⚠️ Implementation-focused |
| **API Tests** | `test_assignments.py` | CRUD operations | ❌ Skipped - auth not implemented |
| **WSGI Test** | `test_wsgi.py` | Deployment entry point works | ❌ Skipped - blueprint re-registration issue |

### What Tests Actually Test

```python
# Example: test_vault_api_response_format
def test_auth_vault_api_response_format(self):
    response = self.client.get("/auth/vaults/vault/")
    # If JSON, it should be parseable
    if response.content_type and 'json' in response.content_type:
        try:
            response_data = response.get_json()
            self.assertIsNotNone(response_data)
        except Exception as e:
            self.fail(f"Failed to parse JSON response: {e}")
```

**Critique:** This tests "response is parseable" NOT "response contains expected data with correct structure". This is too loose to catch real bugs.

### Monkey-Patching Implementation

```python
# flask_test/campus_request.py
class TestCampusRequest(FlaskTestClient):
    """Test-compatible CampusRequest using FlaskTestClient."""

    def __init__(self, base_url: str | None = None, ...):
        # Doesn't look up app at init time - determines per-request
        app = self._get_app_for_base_url(self.base_url, "")
        super().__init__(app, base_url=self.base_url)

    def get(self, path, query=None):
        app = self._get_app_for_request(path)  # Per-request routing
        test_client = app.test_client()
        ...
```

**Critique:** This is clever but complex. It replaces the actual HTTP client with one that routes to Flask test clients based on URL. This creates a parallel test infrastructure that must be kept in sync with the real client.

## Testing Principles vs Current Implementation

| Principle | Current Practice | Gap |
|-----------|-----------------|-----|
| **Test interfaces, not implementation** | Tests internal Flask blueprints, module imports | Tests don't verify HTTP interface contracts |
| **Test behavioral invariants** | Tests check "can import", "has blueprint" | No tests for "unauthorized request returns 401", "invalid JSON returns 400" |
| **Avoid mocks for internal interfaces** | Monkey-patches `campus_python` (external lib) | ✅ Correct approach, but creates maintenance burden |
| **Prefer response validation** | `assert response.status_code == 200` | ✅ Some validation, but often insufficient |

## Recommendations

### 1. Test HTTP Interface Contracts Directly

**Problem:** Current tests test Flask internals (blueprints, routes) rather than HTTP behavior.

**Proposal:** Write tests that verify HTTP request/response contracts:

```python
def test_vault_endpoint_requires_auth(self):
    """GET /auth/v1/vaults/vault/ without auth returns 401."""
    response = self.client.get("/auth/v1/vaults/vault/")
    assert response.status_code == 401
    data = response.get_json()
    assert data["error_code"] == "UNAUTHORIZED"

def test_vault_endpoint_rejects_invalid_token(self):
    """GET /auth/v1/vaults/vault/ with invalid token returns 401."""
    response = self.client.get(
        "/auth/v1/vaults/vault/",
        headers={"Authorization": "Bearer invalid_token"}
    )
    assert response.status_code == 401

def test_vault_endpoint_accepts_valid_credentials(self):
    """Valid credentials can access vault endpoint."""
    response = self.client.get(
        "/auth/v1/vaults/vault/SECRET_KEY",
        headers=self.valid_auth_headers
    )
    assert response.status_code == 200
    assert "key" in response.get_json()
```

### 2. Separate Contract Tests from Implementation Tests

**Problem:** Deployment tests and functional tests are mixed.

**Proposal:** Split into distinct test types:

```
tests/
├── contract/           # HTTP interface contracts (black-box)
│   ├── auth_vault.py   # Auth vault HTTP contract
│   ├── api_assignments.py  # Assignments API contract
│   └── conftest.py     # Fixture: real HTTP client or test container
├── integration/        # Service integration (gray-box)
│   ├── auth_flow.py    # Full OAuth flow tests
│   └── yapper_flow.py  # Event publishing/consuming
└── unit/               # Already exists
```

**Contract Tests:**
- Use real HTTP client (or test container with real services)
- Test HTTP status codes, content-types, error response formats
- Test authentication/authorization at HTTP level
- No mocks for internal interfaces

**Integration Tests:**
- Test service boundaries (auth + storage, api + yapper)
- Test end-to-end flows (OAuth login → token → API call)
- Can use test doubles for external services (Google OAuth)

### 3. Fix the Authentication Testing Gap

**Problem:** API endpoints require bearer tokens (user sessions) but we have no way to create test tokens.

**Option A: Implement Client Credentials Flow**
```python
# campus.auth should support:
POST /auth/v1/token
Content-Type: application/x-www-form-urlencoded
grant_type=client_credentials&client_id=xxx&client_secret=yyy

Response:
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 3600
}
```

**Option B: Direct Token Creation for Tests**
```python
# In test fixtures:
from campus.auth.resources.credentials import credentials

def create_test_token(user_id, scopes=None) -> str:
    """Create a test bearer token for the given user."""
    return credentials["campus"][user_id].new(
        client_id=env.CLIENT_ID,
        scopes=scopes or [],
        expiry_seconds=3600
    ).id
```

**Recommendation:** Implement Option B for tests (simpler), add Option A for production use.

### 4. Eliminate Monkey-Patching with Test Containers

**Problem:** Monkey-patching `campus_python.CampusRequest` is complex and fragile.

**Alternative:** Use Docker test containers with real services:

```python
# conftest.py for contract tests
import pytest

@pytest.fixture(scope="session")
def auth_service():
    """Run campus.auth in a Docker container for testing."""
    # Docker Compose to start services
    yield "http://localhost:8080"
    # Cleanup: stop containers

@pytest.fixture(scope="session")
def api_service(auth_service):
    """Run campus.api in a Docker container, configured to use auth_service."""
    yield "http://localhost:8081"
```

**Benefits:**
- Tests real HTTP behavior
- No monkey-patching required
- Catches deployment configuration issues
- Tests can be run against any environment (local, staging)

**Trade-offs:**
- Slower than in-memory tests
- Requires Docker/Testcontainers setup
- External service dependencies (can be mitigated with test fixtures)

### 5. Define Clear Test Invariants

**Problem:** Tests are loosely defined ("can it be deployed", "some routes exist").

**Proposal:** Define explicit invariants for each service:

**Auth Service Invariants:**
1. All endpoints require authentication (401 without auth header)
2. Invalid client credentials return 401 with specific error format
3. Valid client credentials can access vault endpoints
4. Vault endpoints return structured errors for missing keys
5. OAuth endpoints redirect to Google with correct parameters

**API Service Invariants:**
1. All endpoints require bearer token authentication
2. Invalid/expired tokens return 401 with specific error format
3. Valid tokens allow access to permitted resources
4. Request validation errors return 400 with field-level details
5. Resource not found returns 409 (Campus convention)
6. CORS headers present for allowed origins

### 6. Improve Test Fixtures

**Problem:** Test fixtures are complex and require deep internal knowledge.

**Proposal:** Create simpler, intent-revealing fixtures:

```python
# tests/contract/fixtures.py
import pytest

@pytest.fixture
def auth_client():
    """Create an authenticated client for campus.auth."""
    from campus.auth import resources as auth_resources

    # Create test client
    client = auth_resources.client.new(
        name="test-contract-client",
        description="Client for contract tests"
    )
    secret = auth_resources.client[client.id].revoke()

    yield {
        "client_id": client.id,
        "client_secret": secret,
        "auth_headers": {
            "Authorization": f"Basic {base64.b64encode(f'{client.id}:{secret}').decode()}"
        }
    }

    # Cleanup
    auth_resources.client[client.id].delete()

@pytest.fixture
def user_token(auth_client):
    """Create a test user with bearer token."""
    from campus.auth.resources.credentials import credentials

    user_id = "test-user@campus.test"
    token = credentials["campus"][user_id].new(
        client_id=auth_client["client_id"],
        scopes=["read", "write"],
        expiry_seconds=3600
    )

    yield {
        "user_id": user_id,
        "token": token.id,
        "auth_headers": {
            "Authorization": f"Bearer {token.id}"
        }
    }
```

### 7. Eliminate Shared State

**Problem:** `ServiceManager` uses shared instances causing state pollution.

**Proposal:** Each test class gets fresh fixtures:

```python
# Use pytest fixtures instead of ServiceManager
@pytest.fixture(scope="class")
def services(auth_client):
    """Set up services for a test class."""
    import campus.auth
    from campus.common import devops

    # Create fresh Flask apps
    auth_app = devops.deploy.create_app(campus.auth)

    # Register with test client
    register_test_app("https://campus.test", auth_app, path_prefix="/auth")

    yield {"auth_app": auth_app}

    # Cleanup: reset storage
    reset_test_storage()
```

## Implementation Priority

1. **Quick Wins (can do now):**
   - Add HTTP contract tests for auth vault endpoints
   - Add error response format tests (401, 409, 400)
   - Make `auth.init()` and `yapper.init()` truly idempotent

2. **Medium Term:**
   - Implement token creation fixture for bearer token tests
   - Re-enable `test_assignments.py` with bearer auth
   - Add contract tests for API endpoints

3. **Long Term:**
   - Evaluate Docker/testcontainers approach
   - Separate contract tests from integration tests
   - Define and document test invariants

## Open Questions

1. **Service-to-Service Auth:** Should campus.api support client credentials grant for internal service communication? Currently it only supports user session tokens.

2. **Test Isolation:** Should each test get a fresh database (slower, isolated) or share a database (faster, but state pollution risk)?

3. **External Dependencies:** Contract tests with real services vs. mocked services. Where to draw the line?

4. **Blueprint State:** Flask blueprints can't be reconfigured after registration. This affects how we structure test teardown.

## Conclusion

The current integration test infrastructure has good bones (ServiceManager pattern, test backends) but suffers from:
- Over-reliance on monkey-patching
- Testing implementation rather than HTTP contracts
- Authentication testing gap (no bearer token support)
- Shared state causing fragility

The recommended refactor moves towards:
- HTTP contract testing with clear invariants
- Simpler fixtures without complex shared state
- Explicit token creation for bearer auth tests
- Separation of concerns (contract vs integration vs unit)
