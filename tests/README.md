# Campus Test Directories

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

## Usage Examples

### Running All Unit Tests
```bash
# Run all unit tests (reliable, no external dependencies)
poetry run python -m unittest discover tests/unit -v
```

### Running Package-Specific Unit Tests
```bash
# Test only campus.apps unit tests
poetry run python -m unittest discover tests/unit/apps -v

# Test only campus.vault unit tests  
poetry run python -m unittest discover tests/unit/vault -v

# Test only campus.yapper unit tests
poetry run python -m unittest discover tests/unit/yapper -v
```

### Running Integration Tests
```bash
# Run all integration tests (may require environment setup)
poetry run python -m unittest discover tests/integration -v

# Run integration tests for specific package
poetry run python -m unittest discover tests/integration/apps -v
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
poetry run python -m unittest discover tests -v
```

## Quick Start

For development, typically run unit tests only as they are fast and reliable:
```bash
poetry run python -m unittest discover tests/unit
```

For CI/CD or comprehensive testing, run the full suite:
```bash
poetry run python -m unittest discover tests
```

## Test Scripts

Use the convenience script for common test scenarios:
```bash
# Run the test runner script
./scripts/run_tests.sh
```
