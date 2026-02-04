# Contract Tests

HTTP contract tests verify the interface contracts for Campus API endpoints. These tests
focus on external behavior rather than implementation details.

## What Contract Tests Verify

Contract tests validate **behavioral invariants** - guarantees that the API makes about
its HTTP interface:

1. **Status codes** - Correct HTTP status for success/error cases
2. **Response formats** - Consistent JSON structure for responses
3. **Authentication** - Auth requirements and error handling
4. **Validation** - Request validation and error response formats

## Test Files

### Auth Service Contracts

| File | Invariants Tested |
|------|-------------------|
| `test_auth_vault.py` | Vault CRUD requires auth, returns 401 without, 404 for missing keys |
| `test_auth_clients.py` | Client CRUD, validation, access control |
| `test_auth_credentials.py` | Token creation, bearer token validation |
| `test_auth_sessions.py` | Session lifecycle, OAuth flow |
| `test_auth_users.py` | User CRUD, activation flows |
| `test_auth_logins.py` | Login endpoint redirects, error handling |

### API Service Contracts

| File | Invariants Tested |
|------|-------------------|
| `test_api_assignments.py` | Assignment CRUD, auth requirements, 409 for not found |
| `test_api_circles.py` | Circle CRUD, member management |
| `test_api_submissions.py` | Submission CRUD, classroom link handling |
| `test_api_emailotp.py` | Email OTP generation, validation |

## HTTP Invariants by Service

### Auth Service (`/auth/v1/*`)

All endpoints must:
- Return **401** without valid `Authorization` header
- Return **409** (Conflict) when resource not found (Campus convention)
- Return **400** (Bad Request) for invalid request bodies
- Include structured error responses with `error_code` field

**Vault endpoints** (`/auth/v1/vaults/*`):
- Require Basic auth with `CLIENT_ID` and `CLIENT_SECRET`
- `GET /vaults/{label}/` → 200 with `{"keys": [...]}`
- `GET /vaults/{label}/{key}` → 200 with `{"key": "value"}` or 404
- `POST /vaults/{label}/{key}` → 200 with `{"key": "value"}`
- `DELETE /vaults/{label}/{key}` → 200

### API Service (`/api/v1/*`)

All endpoints must:
- Require **Bearer token** authentication (user session)
- Return **401** without valid token
- Return **409** (Conflict) when resource not found
- Return **400** for validation errors

**Assignments endpoints** (`/api/v1/assignments/*`):
- `GET /assignments/` → 200 with `{"data": [...]}`
- `GET /assignments/{id}` → 200 with assignment resource or 409
- `POST /assignments/` → 201 with created assignment
- `PATCH /assignments/{id}` → 200 with updated assignment
- `DELETE /assignments/{id}` → 200

## Running Contract Tests

```bash
# Run all contract tests
poetry run python -m unittest discover -s tests/contract -p "test_*.py"

# Run specific contract test
poetry run python -m unittest tests.contract.test_auth_vault -v

# Run with verbose output
poetry run python -m unittest discover -s tests/contract -v
```

## Writing New Contract Tests

When adding new endpoints, create corresponding contract tests:

1. **Test unauthenticated access** returns 401
2. **Test not found case** returns 409 (or 404 for vault)
3. **Test validation errors** return 400 with error details
4. **Test success case** returns expected response format
5. **Test required fields** are enforced

Example:
```python
def test_endpoint_requires_auth(self):
    """GET /endpoint without auth returns 401."""
    response = self.client.get("/api/v1/endpoint")
    assert response.status_code == 401
    data = response.get_json()
    assert data["error_code"] == "UNAUTHORIZED"

def test_endpoint_not_found_returns_409(self):
    """GET /endpoint/{id} for missing id returns 409."""
    response = self.client.get(
        "/api/v1/endpoint/does_not_exist",
        headers=self.auth_headers
    )
    assert response.status_code == 409
```

## Test Fixtures

Contract tests use fixtures from `tests.fixtures`:

- `services.create_service_manager()` - Sets up test services
- `create_test_token(user_id)` - Creates bearer tokens for testing
- `get_bearer_auth_headers(token)` - Creates auth headers
- `get_basic_auth_headers(client_id, secret)` - Creates Basic auth headers

See [tests/fixtures/README.md](../fixtures/README.md) for details.
