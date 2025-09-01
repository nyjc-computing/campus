
# Campus Test Directories

## Critical Information

- The test suite **only uses the standard library `unittest` module**—no other test dependencies are required or supported.
- **All tests must be run using the Poetry environment.** Do not create or activate new virtual environments manually.
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

## Directory Structure

```
tests/
  unit/                 # Unit tests (no external dependencies)
    apps/
      test_client.py    # Client interface tests
      test_models.py    # Model logic tests  
      test_routes.py    # Route logic tests
    vault/
      test_client.py    # Client interface tests
      test_models.py    # Model logic tests
      test_routes.py    # Route logic tests
    yapper/
      test_models.py    # Model logic tests
    common/             # Tests for campus.common
      test_introspect.py
      test_validation.py
    client/             # Tests for campus.client
      test_base.py      # HttpClient base functionality
  integration/          # Integration tests (require environment setup)
    apps/
      test_models_users.py
      test_models_circles.py
    vault/
      test_vault_integration.py
    yapper/
      test_yapper.py
```

## Usage Examples


### Running All Unit Tests
```bash
# Run all unit tests (reliable, no external dependencies)
poetry run python tests/run_tests.py unit
```


### Running Package-Specific Unit Tests
```bash
# Test only campus.apps unit tests
poetry run python tests/run_tests.py unit --module apps

# Test only campus.vault unit tests  
poetry run python tests/run_tests.py unit --module vault

# Test only campus.yapper unit tests
poetry run python tests/run_tests.py unit --module yapper

# Test only campus.common unit tests
poetry run python tests/run_tests.py unit --module common

# Test only campus.client unit tests
poetry run python tests/run_tests.py unit --module client
```


### Running Integration Tests
```bash
# Run all integration tests (may require environment setup)
poetry run python tests/run_tests.py integration

# Run integration tests for specific package
poetry run python tests/run_tests.py integration --module apps
```


### Running Specific Test Files
```bash
# Run a specific test file
poetry run python -m unittest tests.unit.apps.test_client -v

# Run a specific test class
poetry run python -m unittest tests.unit.apps.test_client.TestAdminClient -v

# Run a specific test method
poetry run python -m unittest tests.unit.apps.test_client.TestAdminClient.test_init_default_base_url -v
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
python tests/run_tests.py unit --module apps
python tests/run_tests.py unit --module vault
python tests/run_tests.py unit --module common
python tests/run_tests.py integration --module apps

# Verbose output
python tests/run_tests.py unit -v
```
