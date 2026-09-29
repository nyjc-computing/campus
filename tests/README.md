
# Campus Test Directories

> **Comprehensive testing guide:** See [docs/TESTING-GUIDE.md](../docs/TESTING-GUIDE.md) for complete testing documentation including what we test, how tests are organized, and how to write new tests.

## Cross-Platform Support

The test runner and infrastructure supports **Windows, Linux, and macOS** with automatic platform detection:

- **Windows**: Uses `.venv/Scripts/python.exe` and `.venv/Scripts/pyright.exe`
- **Linux/macOS**: Uses `.venv/bin/python` and `.venv/bin/pyright`
- Platform detection is automatic - no manual configuration needed

The `poetry run` pattern works identically across all platforms:
```bash
# Works identically on Windows, Linux, and macOS
poetry run python tests/run_tests.py unit
poetry run python tests/run_tests.py all
```

## Critical Information

- The test suite **only uses the standard library `unittest` module**—no other test dependencies are required or supported.
- **All tests must be run using the Poetry environment.** Do not create or activate new virtual environments manually.
- **Cross-platform compatible**: Tests run on Windows, Linux, and macOS via the test runner.
- **Tests should ideally be invoked through `tests/run_tests.py`** for consistent environment and cross-platform executable detection.

### Which Suites Run Where

| Suite | Runs in CI? | Notes |
|-------|------------|-------|
| sanity | Yes | incl. the discovery guard (`tests/sanity/test_discovery.py`) |
| type | Yes | pyright |
| unit | Yes | `unittest discover tests/unit` |
| integration | Yes | `unittest discover tests/integration` |
| contract | **No — local only** | Compare against the current `weekly` baseline; failures = real bugs |
| performance | No (manual) | `tests/run_tests.py performance` |

CI never runs the contract suite, so a green PR check does **not** mean the
HTTP contracts pass — run it locally before merging endpoint changes.

### Test-File Reachability

unittest discovery silently skips directories without `__init__.py`, and the
sanity runner only executes what `tests/sanity_check.py` imports. The sanity
guard (`tests/sanity/test_discovery.py`) fails when a `tests/**/test_*.py`
file is unreachable by any runner. Deliberately-unreachable files must be
listed in its `UNREACHABLE_ALLOWLIST` with a reason.

### Fixture Lifecycle Gotchas

For the full picture of how cross-service test requests are routed
(transport patching, `register_test_app`, auth-header precedence), see
**"How Cross-Service Test Requests Are Routed"** in
[docs/TESTING-GUIDE.md](../docs/TESTING-GUIDE.md), including a minimal
probe-script skeleton.

- `ServiceManager.clear_test_data()` (called in per-test `setUp`) **wipes the
  credentials storage**. Bearer tokens created once in `setUpClass` are dead
  from the second test on — create tokens in `setUp`, *after* the clear
  (see the api contract fixtures for the pattern).
- Test doubles must mirror production exactly: `tests/flask_test/response.py`
  raises the same `campus_python.errors` classes (via
  `APIError.with_status_code`) that the production client raises, so product
  error-handling code behaves identically under test routing and over the wire.

### Auditing Skip Markers

`python scripts/audit_skipped_tests.py [--reason "API BUG"]` runs skipped
tests with the skip neutralized and reports PASS (stale marker) vs FAIL
(still live). See the Testing Guide's "Skip Markers" policy.

### Poetry Usage Example

To run tests using the Poetry environment, use:

```bash
poetry run python tests/run_tests.py unit
```

Or for a specific test file:

```bash
poetry run python -m unittest tests.unit.apps.test_client -v
```

## Test Organization

### Unit Tests
- Unit tests test only internal logic of each package
- No environment dependencies or cross-package interactions
- Located in tests/unit/<package>/
- Mock external dependencies (may mock `campus.common` classes)
- Must not mock package classes (test real implementations)

### Integration Tests
- Integration tests test package as a whole including DB, API, cross-package interactions
- Use `tests.fixtures.services.create_service_manager()` for environment setup
- Located in tests/integration/<package>/
- Test real implementations with actual dependencies
- Use base classes from `tests/integration/base.py` for consistent setup/teardown
- **Single shared database** across all test classes (aligns with production deployment)
- **Per-test data isolation** via `clear_test_data()` in setUp()

### Contract Tests
- Contract tests verify HTTP interface contracts (status codes, response formats, authentication)
- Test behavioral invariants of the API surface
- Located in tests/contract/
- No mocks for internal interfaces - test real HTTP behavior
- See [tests/contract/README.md](contract/README.md) for invariants tested

## Directory Structure

```
tests/
  unit/                 # Unit tests (no external dependencies)
    auth/
      test_resources.py # Business logic tests
      test_routes.py    # Route logic tests
    api/
      test_resources.py # Business logic tests
      test_routes.py    # Route logic tests
    storage/
      test_tables.py    # Storage layer tests
    yapper/
      test_logging.py   # Logging tests
    common/             # Tests for campus.common
      test_introspect.py
      test_validation.py
  integration/          # Integration tests (require environment setup)
    auth/
      test_auth_integration.py
    api/
      test_assignments.py
    yapper/
      test_yapper.py
  contract/             # HTTP contract tests (interface invariants)
    test_auth_vault.py  # Vault endpoint contracts
    test_auth_clients.py # Client CRUD contracts
    test_auth_*.py      # Other auth contracts
    test_api_*.py       # API endpoint contracts
  fixtures/             # Shared test fixtures
    services.py         # ServiceManager for test coordination
    tokens.py           # Test token creation utilities
  flask_test/           # Flask test client adapters
    campus_request.py   # Test-compatible CampusRequest
```

## Usage Examples


### Running All Unit Tests
```bash
# Run all unit tests (reliable, no external dependencies)
poetry run python tests/run_tests.py unit
```


### Running Package-Specific Unit Tests
```bash
# Test only campus.auth unit tests
poetry run python tests/run_tests.py unit --module auth

# Test only campus.api unit tests
poetry run python tests/run_tests.py unit --module api

# Test only campus.storage unit tests
poetry run python tests/run_tests.py unit --module storage

# Test only campus.yapper unit tests
poetry run python tests/run_tests.py unit --module yapper

# Test only campus.common unit tests
poetry run python tests/run_tests.py unit --module common
```


### Running Integration Tests
```bash
# Run all integration tests (may require environment setup)
poetry run python tests/run_tests.py integration

# Run integration tests for specific package
poetry run python tests/run_tests.py integration --module auth
poetry run python tests/run_tests.py integration --module api
```

### Running Contract Tests
```bash
# Run all contract tests (HTTP interface invariants)
poetry run python -m unittest discover -s tests/contract -p "test_*.py"

# Run specific contract test file
poetry run python -m unittest tests.contract.test_auth_vault -v
```


### Running Specific Test Files
```bash
# Run a specific test file
poetry run python -m unittest tests.unit.auth.test_resources -v

# Run a specific test class
poetry run python -m unittest tests.unit.auth.test_resources.TestAuthResource -v

# Run a specific test method
poetry run python -m unittest tests.unit.auth.test_resources.TestAuthResource.test_authenticate -v
```


### Running All Tests
```bash
# Run complete test suite (unit + integration)
poetry run python tests/run_tests.py all
```


## Quick Start

For development, typically run unit tests only as they are fast and reliable:
```bash
# Using the convenience script (recommended)
poetry run python tests/run_tests.py unit
```

For CI/CD or comprehensive testing, run the full suite:
```bash
# Using the convenience script (recommended)
poetry run python tests/run_tests.py all
```

## Test Scripts

Use the convenience script for common test scenarios:
```bash
# Run only unit tests
poetry run python tests/run_tests.py unit

# Run only integration tests
poetry run python tests/run_tests.py integration

# Run all tests (unit + integration)
poetry run python tests/run_tests.py all

# Test specific modules
poetry run python tests/run_tests.py unit --module auth
poetry run python tests/run_tests.py unit --module api
poetry run python tests/run_tests.py unit --module common
poetry run python tests/run_tests.py integration --module auth

# Verbose output
poetry run python tests/run_tests.py unit -v
```

## More Information

For complete testing documentation including:
- What we test and what we don't test
- How to write new tests
- Test environment setup
- Known gotchas

See [docs/TESTING-GUIDE.md](../docs/TESTING-GUIDE.md).```
