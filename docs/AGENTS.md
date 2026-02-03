# AI Agent Guidelines

This file contains reminders for AI agents (Claude, Copilot, etc.) working on the Campus codebase.

## 🚨 Critical Reminders (Read First!)

1. **Use Poetry for all Python commands**
   - ❌ `python main.py`
   - ✅ `poetry run python main.py`
   - ❌ `python -m unittest discover tests`
   - ✅ `poetry run python run_tests.py`

2. **Use `run_tests.py` as the ONLY test entrypoint**
   - Never run `unittest` or `pytest` directly
   - The test entrypoint handles environment setup, cleanup, and isolation
   - Running tests directly may produce false positives or miss failures
   - Usage: `poetry run python run_tests.py [unit|integration|sanity|type|all]`

3. **Read these files BEFORE starting work**
   - [CONTRIBUTING.md](CONTRIBUTING.md) - Development workflow and branching
   - [GETTING-STARTED.md](GETTING-STARTED.md) - Setup instructions
   - [STYLE-GUIDE.md](STYLE-GUIDE.md) - Code standards and import patterns

4. **Campus uses `unittest`, not `pytest`**
   - Test files use `unittest.TestCase` framework
   - Fixtures are in `tests/fixtures/` directory
   - Test discovery uses `unittest` patterns

## 📁 Key File Locations

### Tests
- `tests/run_tests.py` - **ALWAYS use this to run tests**
- `tests/fixtures/` - Test fixtures and shared utilities
- `tests/unit/` - Unit tests
- `tests/integration/` - Integration tests
- `tests/contract/` - HTTP contract tests (black-box)

### Code
- `campus/` - Main application code
  - `campus/auth/` - Authentication service
  - `campus/api/` - REST API
  - `campus/common/` - Shared utilities
  - `campus/model/` - Entity definitions
  - `campus/storage/` - Data persistence layer

### Docs
- `docs/CONTRIBUTING.md` - How to contribute
- `docs/GETTING-STARTED.md` - Setup guide
- `docs/STYLE-GUIDE.md` - Code standards
- `docs/architecture.md` - System design
- `docs/integration-test-refactor-plan.md` - Test improvement progress

## 🎯 Common Tasks

### Running Tests
```bash
# All tests
poetry run python run_tests.py

# Specific category
poetry run python run_tests.py unit
poetry run python run_tests.py integration
```

### Creating Tests
1. Extend `unittest.TestCase`
2. Place in appropriate directory (`tests/unit/`, `tests/integration/`, `tests/contract/`)
3. Use fixtures from `tests/fixtures/`
4. Run via `run_tests.py` to verify

### Import Patterns (from STYLE-GUIDE.md)
- Import packages, not individual functions
- Use `from campus.common import env` not `from campus.common.env import ENV`
- Lazy imports in tests to avoid early storage initialization

## ⚠️ Known Gotchas

1. **Storage initialization order matters**
   - Test fixtures must lazy-import `campus.storage` modules
   - Otherwise storage backends initialize before test mode

2. **Test isolation requires proper cleanup**
   - Each test class should use `ServiceManager` from `tests/fixtures/services.py`
   - `reset_test_storage()` is called at start of `ServiceManager.setup()`
   - Test clients load credentials dynamically from environment

3. **Flask blueprints can only be registered once**
   - Using `shared=False` with `ServiceManager` causes errors
   - Flask apps are shared across test classes to avoid this

## 📋 Session Checklist

Before starting work, confirm:
- [ ] Read CONTRIBUTING.md
- [ ] Read GETTING-STARTED.md
- [ ] Read STYLE-GUIDE.md
- [ ] Using `poetry run python` for all commands
- [ ] Will use `run_tests.py` for testing
