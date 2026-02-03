
# Campus Test Directories

## Critical Information

- The test suite **only uses the standard library `unittest` module**—no other test dependencies are required or supported.
- **All tests must be run using the Poetry environment.** Do not create or activate new virtual environments manually.
- **Recommended:** Use `poetry run` before any test command, or activate the environment with `poetry shell` and then run your test commands directly.
- **Tests should ideally be invoked through `tests/run_tests.py`** for consistent environment and options.

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
- Use tests.fixtures.setup for environment setup
- Located in tests/integration/<package>/
- Test real implementations with actual dependencies

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
python tests/run_tests.py unit

# Run only integration tests  
python tests/run_tests.py integration

# Run all tests (unit + integration)
python tests/run_tests.py all

# Test specific modules
python tests/run_tests.py unit --module auth
python tests/run_tests.py unit --module api
python tests/run_tests.py unit --module common
python tests/run_tests.py integration --module auth

# Verbose output
python tests/run_tests.py unit -v
```
