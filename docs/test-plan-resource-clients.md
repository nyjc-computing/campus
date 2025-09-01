# Resource Client Test Plan

## Overview

This document outlines the testing strategy for Campus Resource Client libraries, which provide unified interfaces for accessing Campus services (Apps, Vault) through a consistent Resource-based architecture.

## Architecture Under Test

### Resource Pattern
- **Base Resource Class**: `campus.client.interface.Resource`
- **HTTP Client Interface**: `campus.common.http.JsonClient`
- **Response Interface**: `campus.common.http.JsonResponse`
- **Error Handling**: `campus.common.errors.api_errors.*`

### Client Modules
1. **Apps Service**: `campus.client.apps.*`
2. **Vault Service**: `campus.client.vault.*`
3. **Common HTTP**: `campus.common.http.*`

## Testing Strategy

### Unit Testing Principles
Following the guidelines in `tests/README.md`:

- **No Environment Dependencies**: Mock external HTTP calls and services
- **Mock External Dependencies**: Mock `campus.common.http.JsonClient` methods
- **Test Real Implementations**: No mocking of Resource classes themselves
- **Isolated Functionality**: Each test focuses on specific Resource behavior
- **Black-box Testing**: Test only public interfaces

### Test Structure
```
tests/unit/
├── apps/
│   └── test_client.py          # Apps Resource tests
├── client/
│   └── test_base.py            # JsonClient interface tests
├── vault/
│   └── test_client.py          # Vault Resource tests
└── common/
    └── test_http.py            # HTTP client implementation tests
```

## Detailed Test Plans

### 1. Apps Resource Tests (`tests/unit/apps/test_client.py`)

#### AdminResource Tests
**Class**: `TestAdminResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Resource initialization | Mock JsonClient | Verify path="/admin" |
| `test_status()` | GET /admin/status | Mock client.get() | Verify correct endpoint called |
| `test_init_db()` | POST /admin/init-db | Mock client.post() | Verify endpoint + empty JSON body |
| `test_purge_db()` | POST /admin/purge-db | Mock client.post() | Verify endpoint + empty JSON body |
| `test_make_path()` | Path construction | No mocking | Verify path building logic |

#### UsersResource Tests
**Class**: `TestUsersResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Resource initialization | Mock JsonClient | Verify path="/users" |
| `test_getitem()` | User indexing access | No mocking | Verify UserResource returned |
| `test_new()` | POST /users/ | Mock client.post() | Verify data payload format |
| `test_new_required_fields()` | Validation | No mocking | Verify TypeError on missing fields |

#### UserResource Tests
**Class**: `TestUserResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Individual user resource | No mocking | Verify path construction |
| `test_get()` | GET /users/{id} | Mock client.get() | Verify correct path |
| `test_update()` | PATCH /users/{id} | Mock client.patch() | Verify JSON payload |
| `test_delete()` | DELETE /users/{id} | Mock client.delete() | Verify correct path |
| `test_profile()` | GET /users/{id}/profile | Mock client.get() | Verify profile endpoint |

#### CirclesResource Tests
**Class**: `TestCirclesResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Resource initialization | Mock JsonClient | Verify path="/circles" |
| `test_getitem()` | Circle indexing access | No mocking | Verify CircleResource returned |
| `test_list()` | GET /circles | Mock client.get() | Verify parameters passed |
| `test_list_with_filters()` | GET /circles?filters | Mock client.get() | Verify query parameters |
| `test_new()` | POST /circles | Mock client.post() | Verify required fields |

#### CircleResource Tests
**Class**: `TestCircleResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Individual circle resource | No mocking | Verify path construction |
| `test_get()` | GET /circles/{id} | Mock client.get() | Verify correct path |
| `test_update()` | PATCH /circles/{id} | Mock client.patch() | Verify JSON payload |
| `test_delete()` | DELETE /circles/{id} | Mock client.delete() | Verify correct path |
| `test_move()` | POST /circles/{id}/move | Mock client.post() | Verify parent_circle_id |
| `test_move_self_reference()` | Validation | No mocking | Verify ValueError raised |
| `test_members_property` | Sub-resource access | No mocking | Verify CircleMembers returned |

#### CircleMembers Tests
**Class**: `TestCircleMembers`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_list()` | GET /circles/{id}/members | Mock client.get() | Verify correct path |
| `test_add()` | POST /circles/{id}/members/add | Mock client.post() | Verify member_id + kwargs |
| `test_remove()` | DELETE /circles/{id}/members/remove | Mock client.delete() | Verify member_id payload |
| `test_set()` | PUT /circles/{id}/members/set | Mock client.put() | Verify access_value |

### 2. Vault Resource Tests (`tests/unit/vault/test_client.py`)

#### VaultResource Tests
**Class**: `TestVaultResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Resource initialization | Mock JsonClient | Verify path="/vault" |
| `test_getitem()` | Vault collection access | No mocking | Verify Vault returned |
| `test_list()` | GET /vault | Mock client.get() | Verify vault labels |
| `test_access_property` | Sub-resource access | No mocking | Verify VaultAccessResource |
| `test_clients_property` | Sub-resource access | No mocking | Verify VaultClientResource |

#### Vault Tests
**Class**: `TestVault`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Vault collection | No mocking | Verify path="/vault/{label}" |
| `test_getitem()` | Key access | No mocking | Verify VaultKeyResource returned |
| `test_list()` | GET /vault/{label} | Mock client.get() | Verify key listing |

#### VaultKeyResource Tests
**Class**: `TestVaultKeyResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Individual key resource | No mocking | Verify path construction |
| `test_get()` | GET /vault/{label}/{key} | Mock client.get() | Verify secret retrieval |
| `test_set()` | POST /vault/{label}/{key} | Mock client.post() | Verify value payload |
| `test_delete()` | DELETE /vault/{label}/{key} | Mock client.delete() | Verify correct path |

#### VaultAccessResource Tests
**Class**: `TestVaultAccessResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Access management resource | No mocking | Verify path="/vault/access" |
| `test_grant()` | POST /vault/access/{label} | Mock client.post() | Verify permissions payload |
| `test_revoke()` | DELETE /vault/access/{label} | Mock client.delete() | Verify client_id |
| `test_check()` | GET /vault/access/{label} | Mock client.get() | Verify params |

#### VaultClientResource Tests
**Class**: `TestVaultClientResource`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_init` | Client management resource | No mocking | Verify path="/vault/clients" |
| `test_new()` | POST /vault/clients | Mock client.post() | Verify name/description |
| `test_list()` | GET /vault/clients | Mock client.get() | Verify client listing |
| `test_delete()` | DELETE /vault/clients/{id} | Mock client.delete() | Verify client_id |

### 3. HTTP Client Tests (`tests/unit/client/test_base.py`)

#### JsonClient Interface Tests
**Class**: `TestJsonClient`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_get_client()` | Client factory | No mocking | Verify client instance |
| `test_get_client_caching()` | Client reuse | No mocking | Verify same instance returned |
| `test_client_methods()` | Interface compliance | No mocking | Verify all HTTP methods exist |
| `test_base_url_handling()` | URL management | No mocking | Verify base URL setting |

### 4. Error Handling Tests

#### Error Response Tests
**Class**: `TestErrorHandling`

| Test Method | Purpose | Mock Strategy | Assertions |
|-------------|---------|---------------|------------|
| `test_not_found_error()` | 404 responses | Mock client to raise NotFoundError | Verify proper exception propagation |
| `test_unauthorized_error()` | 401 responses | Mock client to raise UnauthorizedError | Verify authentication errors |
| `test_forbidden_error()` | 403 responses | Mock client to raise ForbiddenError | Verify access denied errors |
| `test_validation_error()` | 400 responses | Mock client to raise InvalidRequestError | Verify validation failures |
| `test_conflict_error()` | 409 responses | Mock client to raise ConflictError | Verify conflict handling |

## Mock Strategy Guidelines

### What to Mock
1. **JsonClient HTTP methods** (`get`, `post`, `put`, `patch`, `delete`)
2. **JsonResponse objects** (return mock responses with `.json()`, `.status_code`)
3. **External service dependencies** (configuration, network calls)

### What NOT to Mock
1. **Resource classes** (AdminResource, UsersResource, etc.)
2. **Resource initialization** (test real constructors)
3. **Path building logic** (test real `make_path()` methods)
4. **Resource composition** (test real `__getitem__` and property accessors)

### Mock Examples

```python
# Mock HTTP client method
def test_admin_status(self):
    mock_client = Mock()
    mock_response = Mock()
    mock_response.json.return_value = {"status": "healthy"}
    mock_client.get.return_value = mock_response
    
    admin = AdminResource(mock_client)
    result = admin.status()
    
    mock_client.get.assert_called_once_with("admin/status")
    self.assertEqual(result, mock_response)

# Mock error response
def test_vault_key_not_found(self):
    mock_client = Mock()
    mock_client.get.side_effect = NotFoundError("Key not found")
    
    vault_key = VaultKeyResource(mock_client, "SECRET_KEY")
    
    with self.assertRaises(NotFoundError):
        vault_key.get()
```

## Test Data Fixtures

### Standard Test Data
```python
# User data
VALID_USER_DATA = {"email": "test@example.com", "name": "Test User"}

# Circle data  
VALID_CIRCLE_DATA = {"name": "Test Circle", "description": "Test Description"}

# Vault secret data
VALID_SECRET_DATA = {"value": "secret123"}

# Error responses
NOT_FOUND_RESPONSE = {"error": "Resource not found", "status": 404}
VALIDATION_ERROR_RESPONSE = {"error": "Invalid data", "details": {...}}
```

## Coverage Requirements

### Minimum Coverage Targets
- **Resource Classes**: 95% line coverage
- **HTTP Methods**: 100% coverage of all HTTP verbs
- **Error Paths**: 90% coverage of error handling
- **Path Construction**: 100% coverage of URL building

### Coverage Exclusions
- **Type hints and protocol definitions**
- **Abstract method definitions**
- **Debug logging statements**

## Continuous Integration

### Test Execution
```bash
# Unit tests only (fast, no external dependencies)
poetry run python tests/run_tests.py unit

# Specific module testing
poetry run python tests/run_tests.py unit --module apps
poetry run python tests/run_tests.py unit --module vault  
poetry run python tests/run_tests.py unit --module client

# With verbose output
poetry run python tests/run_tests.py unit --verbose
```

### Success Criteria
- ✅ All unit tests pass
- ✅ No import errors or module not found errors
- ✅ Tests complete in under 10 seconds
- ✅ No external network calls or database dependencies
- ✅ Coverage targets met for all modules

## Future Enhancements

### Phase 2: Advanced Testing
1. **Property-based testing** with `hypothesis` for data validation
2. **Contract testing** to verify API compatibility
3. **Performance testing** for client response times
4. **Thread safety testing** for concurrent client usage

### Phase 3: Integration Testing
1. **End-to-end workflows** using real services
2. **Cross-service interactions** (Apps ↔ Vault)
3. **Authentication flow testing**
4. **Load testing** with multiple concurrent clients

This test plan ensures comprehensive coverage of the Resource client architecture while maintaining fast, reliable unit tests that support continuous development.
