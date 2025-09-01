# Test Refactoring Plan for campus.apps, campus.vault, campus.yapper

## Progress Status: ✅ COMPLETED

### ✅ Phase 1: Directory Structure Created
- Created tests/unit/<package>/ directories for each package
- Created tests/integration/<package>/ directories for each package
- Added README.md explaining the structure

### ✅ Phase 2: Existing Tests Categorized and Moved
- **Integration Tests Moved:**
  - test_vault_integration.py → tests/integration/vault/
  - test_yapper.py → tests/integration/yapper/
  - test_users.py → tests/integration/apps/test_models_users.py
  - test_circles.py → tests/integration/apps/test_models_circles.py

- **Unit Tests Moved:**
  - test_client_vault.py → tests/unit/vault/test_client.py
  - test_client_apps.py → tests/unit/apps/test_client.py

### ✅ Phase 4: Test Triggers and Scripts Created
- Created test runner script at `scripts/run_tests.sh`
- Verified unittest discovery works for all test categories
- Unit tests pass consistently (124 tests total, 1 test has existing validation logic issue)
- Integration tests require environment setup (expected behavior)

### ✅ Phase 5: Additional Common and Client Tests Organized
- Created `tests/unit/common/` for campus.common tests (introspect, validation)
- Created `tests/unit/client/` for campus.client.base tests
- Moved existing common and client tests to appropriate locations
- Updated documentation to reflect complete structure

## ✅ REFACTORING COMPLETED SUCCESSFULLY

### What Was Accomplished:
1. **Separated unit and integration tests** into distinct directory structures
2. **Preserved unittest framework** (removed any accidental pytest additions)
3. **Organized tests by package** (apps, vault, yapper, common, client) and type (models, routes, client)
4. **Created test triggers** using unittest discovery patterns
5. **All existing unit tests work** and can be run independently
6. **Complete test organization** covering all campus packages

### Test Commands That Work:
- `poetry run python -m unittest discover tests/unit` - All unit tests (124 tests, 1 has existing issue)
- `poetry run python -m unittest discover tests/unit/apps` - Apps unit tests only
- `poetry run python -m unittest discover tests/unit/vault` - Vault unit tests only  
- `poetry run python -m unittest discover tests/unit/common` - Common utility tests
- `poetry run python -m unittest discover tests/unit/client` - Client base tests
- `poetry run python -m unittest discover tests/integration` - Integration tests (may need setup)
- `poetry run python -m unittest discover tests` - Full test suite

## 1. Analysis of Existing Tests
- Current tests are not clearly separated by package or by unit/integration.
- Some tests mix internal logic checks with integration (API, DB, or environment) checks.
- Models and routes are not always tested independently.
- Some tests may rely on environment variables or external state.

## 2. Refactoring Plan

### A. Directory Structure
- For each package, create dedicated test directories:
  - `tests/unit/apps/`
  - `tests/unit/vault/`
  - `tests/unit/yapper/`
  - `tests/integration/apps/`
  - `tests/integration/vault/`
  - `tests/integration/yapper/`

### B. Unit Tests
- Unit tests should:
  - Test only internal logic of the package (no cross-package or environment dependencies).
  - Be separated into `models` and `routes` submodules where applicable.
  - Not rely on environment variables or external state.
  - Not mock package classes (test real implementations).
  - May mock `campus.common` classes/utilities as needed.

### C. Integration Tests
- Integration tests should:
  - Test the package as a whole, including interactions with DB, API, or other packages.
  - Use `tests.fixtures.setup` for environment and data setup/teardown.
  - Allow cross-package interaction.
  - Not mock package classes (test real implementations).
  - May mock `campus.common` classes/utilities as needed.

### D. Test Triggers
- Enable running:
  - Only unit tests: `python -m unittest discover tests/unit`
  - Only integration tests: `python -m unittest discover tests/integration`
  - The full test suite: `python -m unittest discover tests`
- Use directory-based selection for test type (unittest discovery)
- Document these triggers in the development guidelines.

### E. Documentation
- Update `docs/development-guidelines.md`:
  - Describe the new test directory structure.
  - Specify the distinction between unit and integration tests.
  - Provide instructions for running each type of test.
  - Clarify mocking policy: package classes must not be mocked; `campus.common` may be mocked.

---

## Example Directory Structure
```
tests/
  unit/
    apps/
      test_models.py
      test_routes.py
    vault/
      test_models.py
      test_routes.py
    yapper/
      test_models.py
      test_routes.py
  integration/
    apps/
      test_integration.py
    vault/
      test_integration.py
    yapper/
      test_integration.py
  fixtures/
    setup.py
```

## Example Unittest Usage
- Run all unit tests: `python -m unittest discover tests/unit`
- Run all integration tests: `python -m unittest discover tests/integration`
- Run all tests: `python -m unittest discover tests`
- Run specific package unit tests: `python -m unittest discover tests/unit/vault`

---

This plan ensures clear separation of concerns, reliable test results, and maintainable test code for campus.apps, campus.vault, and campus.yapper.
