# Campus Quick Reference

Essential reminders for working on the Campus codebase. This guide applies to both humans and AI assistants—everyone should follow the same workflow and principles.

## Critical Reminders (Read First!)

### 1. Use Poetry for All Python Commands

Campus uses Poetry for dependency management. Never run Python directly.

```bash
# Correct
poetry run python main.py
poetry run python tests/run_tests.py unit

# Incorrect
python main.py
python -m unittest discover tests
```

### 2. Use `run_tests.py` for Testing

The only supported test entrypoint is `tests/run_tests.py`. It handles environment setup, cleanup, and isolation. Running tests directly may produce false positives.

```bash
# Run all tests
poetry run python tests/run_tests.py all

# Run specific category
poetry run python tests/run_tests.py unit
poetry run python tests/run_tests.py integration
```

### 3. Campus Uses `unittest`, Not pytest

Test files use the standard library `unittest.TestCase` framework. No pytest dependencies are installed.

### 4. Read These Files Before Starting Work

| File | Purpose |
|------|---------|
| [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) | Setup and navigation |
| [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) | Development workflow and branching |
| [docs/STYLE-GUIDE.md](docs/STYLE-GUIDE.md) | Code standards and import patterns |
| [docs/TESTING-GUIDE.md](docs/TESTING-GUIDE.md) | Testing strategies and how to run tests |
| [docs/development-guidelines.md](docs/development-guidelines.md) | Architecture patterns and gotchas |

## Project Structure

For detailed file locations and architecture, see:
- [docs/architecture.md](docs/architecture.md) - System design and service boundaries
- [campus/README.md](campus/README.md) - Package-level documentation

## Quick Links

### Tests
- [docs/TESTING-GUIDE.md](docs/TESTING-GUIDE.md) - Complete testing guide
- [tests/README.md](tests/README.md) - Test directory reference
- [tests/contract/README.md](tests/contract/README.md) - HTTP contract invariants

### Code Standards
- [docs/STYLE-GUIDE.md](docs/STYLE-GUIDE.md) - Import patterns, docstrings, commit messages
- [docs/development-guidelines.md](docs/development-guidelines.md) - Architecture patterns, common pitfalls

### Getting Started
- [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) - Installation and setup
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) - Branching strategy and workflow

## Known Gotchas

These are the things most commonly forgotten—even by experienced developers:

### Storage Initialization Order

Test fixtures must lazy-import `campus.storage` modules. Otherwise storage backends initialize before test mode is set.

```python
# Bad - initializes storage immediately
from campus.storage import tables

# Good - lazy import in test method
def test_something(self):
    from campus.storage import tables
```

### Flask Blueprint Registration

Flask blueprints can only be registered once. The test infrastructure shares Flask apps across test classes to avoid "already registered" errors.

### Import Patterns

Import packages, not individual functions. This preserves context and prevents naming conflicts.

```python
# Good
from campus.common import utils, devops

# Bad - loses context
from campus.common.utils import uid, utc_time
```

See [docs/STYLE-GUIDE.md](docs/STYLE-GUIDE.md) for complete import guidelines.

## Before You Start

- [ ] Have you read the relevant documentation?
- [ ] Are you using `poetry run python` for all commands?
- [ ] Will you use `run_tests.py` for testing?
- [ ] Do you understand the storage-model-resources pattern?

---

**New to Campus?** Start with [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md).
