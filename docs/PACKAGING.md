# Campus Packaging Guide

## Overview

Campus uses a **monorepo with centralized dependencies** approach. All components are versioned together and distributed as a single package through Git-based dependencies.

**Key Benefits:**
- Consistent versioning across all services
- Simplified dependency management
- Clean modular structure
- No PyPI publishing delays

## Architecture

### Monorepo Structure

Campus consolidates all services in a single repository with unified dependency management in the root `pyproject.toml`:
- Eliminates complex inter-service dependency management
- Ensures compatibility between components
- Simplifies distribution and testing

### Branch Strategy

```
weekly → staging → main
```
- **`weekly`**: Active development, expected breakage
- **`staging`**: Extended testing, pre-production validation
- **`main`**: Stable, production-ready releases

## Dependency Rules

```
auth, api → services, storage, model, common
storage → common
model → common
yapper → (nothing — self-contained)
```

**Key Constraints:**
- `auth` and `api` contain business logic in `.resources` submodules
- `model` contains only entity definitions (minimal dependencies)
- `storage` provides backend-agnostic persistence
- `common` is self-contained
- `yapper` is self-contained: it imports no campus package; its event
  database URI arrives via argument, provider callable, or environment
  ([yapper.md](yapper.md))

## Namespace Package Rules (PEP 420)

The `campus` import namespace is a **native namespace package**: no
distribution ships a `campus/__init__.py`. Python merges every `campus/`
directory found on `sys.path` into one virtual package, so each
distribution owns its own subtree and consumers import one flat namespace:

- `campus-suite` ships `campus/auth/`, `campus/api/`, `campus/model/`, ...
- `campus-common` (planned, #970 phase 3) will ship `campus/common/`

Rules:

- Never add `campus/__init__.py` to any distribution. One stale regular
  package shadows every other dist's portions **silently** — imports
  resolve from the wrong place with no error at install time.
- Each distribution's own subpackages (`campus/common/`, `campus/auth/`,
  ...) remain regular packages with their own `__init__.py`; only the
  shared ancestor level is init-less.
- After `poetry build`, audit the wheels:

  ```bash
  python scripts/audit_wheel_namespace.py
  ```

- When upgrading environments across this conversion, rebuild venvs
  instead of layering installs: leftover `campus/` directories or
  `__pycache__`-only portion dirs from older installs keep serving stale
  imports under the merged namespace.

The `campus_python` client library uses a separate top-level namespace and
is unaffected by these rules.

## Installation

### For Production Use

Add to your `pyproject.toml`:

```toml
[tool.poetry.dependencies]
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "main"}
```

### For Development Integration

```toml
[tool.poetry.group.dev-dependencies]
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "weekly"}
```

### CLI Installation

```bash
# Production (stable)
poetry add git+https://github.com/nyjc-computing/campus.git@main

# Development (bleeding edge)
poetry add git+https://github.com/nyjc-computing/campus.git@weekly --group dev

# Specific commit (reproducible builds)
poetry add git+https://github.com/nyjc-computing/campus.git@abc123def456
```

### Client Library Installation

```bash
# Add campus_python client library
poetry add git+https://github.com/nyjc-computing/campus-api-python.git@main
```

## Using Campus in External Projects

```bash
# Add Campus as dependency
poetry add git+https://github.com/nyjc-computing/campus.git@main

# Add campus_python client library
poetry add git+https://github.com/nyjc-computing/campus-api-python.git@main

# Import and use
python -c "import campus_python; campus = campus_python.Campus()"
```

## Building and Validation

### Local Development

```bash
# Install dependencies
poetry install

# Test imports
poetry run python -c "import campus.auth, campus.api, campus.storage, campus.model"

# Run tests
poetry run python tests/run_tests.py unit
```

### Release Process

1. **Development**: Work in `weekly` branch
2. **Integration**: Merge `weekly` → `staging` for extended testing
3. **Release**: Merge `staging` → `main` when stable
4. **Tagging**: Create version tags on `main` branch

### Dependency Updates

Update dependencies in root `pyproject.toml`:

```bash
# Update a specific package
poetry add requests@^2.31.0

# Update all packages
poetry update

# Lock dependencies
poetry lock
```

## Troubleshooting

### Import Errors

Ensure you're using `poetry run python` instead of system Python.

### Dependency Conflicts

Update to latest main branch:
```bash
poetry add campus-suite@git+https://github.com/nyjc-computing/campus.git@main
```

### Authentication Issues

Verify GitHub access for private repositories:
```bash
git config --global url."https://username:token@github.com/".insteadOf "https://github.com/"
```

### Validation Commands

```bash
# Check environment
poetry env info

# Test installation
poetry run python -c "import campus"

# Test modules
poetry run python -c "import campus.auth; import campus.api; import campus.storage"
```

## Why Git Dependencies?

Campus currently uses Git-based dependencies for active development. This approach provides immediate availability of changes and branch-based stability levels. When Campus stabilizes, we plan to publish to PyPI for stable releases while maintaining Git dependencies for bleeding-edge access.
