# Campus Packaging Guide

## Overview

Campus uses a **monorepo with centralized dependencies** approach. All components are versioned together and distributed as a single package through Git-based dependencies.

**Key Benefits:**
- Consistent versioning across all services
- Simplified dependency management  
- Clean modular structure
- No PyPI publishing delays

## Architecture Decisions

### Monorepo Structure
Campus consolidates all services in a single repository with unified dependency management in the root `pyproject.toml`. This solves several challenges:
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
```

**Key Constraints**:
- `auth` and `api` contain business logic in `.resources` submodules
- `model` contains only entity definitions (minimal dependencies)
- `storage` provides backend-agnostic persistence
- `common` is self-contained

## Installation

### Production Use
```toml
[tool.poetry.dependencies]
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "main"}
```

### Development Integration
```toml
[tool.poetry.group.dev.dependencies]  
campus-suite = {git = "https://github.com/nyjc-computing/campus.git", branch = "weekly"}
```

### CLI Installation
```bash
# Production
poetry add git+https://github.com/nyjc-computing/campus.git@main

# Development
poetry add git+https://github.com/nyjc-computing/campus.git@weekly --group dev

# Specific commit (reproducible builds)
poetry add git+https://github.com/nyjc-computing/campus.git@abc123def456
```

### Client Library Installation
```bash
# Add campus_python client library
poetry add git+https://github.com/nyjc-computing/campus-api-python.git@main
```

## Development Workflow

### Contributing to Campus
```bash
# Clone repository
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Install dependencies
poetry install

# Create feature branch from weekly
git checkout weekly
git checkout -b feature/new-feature

# Make changes, test, submit PR to weekly
```

### Using Campus in External Projects
```bash
# Add Campus as dependency
poetry add git+https://github.com/nyjc-computing/campus.git@main

# Add campus_python client library
poetry add git+https://github.com/nyjc-computing/campus-api-python.git@main

# Import and use
python -c "import campus_python; campus = campus_python.Campus()"
```

## Building and Distribution

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

### Common Issues

**Import errors**: Ensure you're using `poetry run python` instead of system Python.

**Dependency conflicts**: Update to latest main branch:
```bash
poetry add campus-suite@git+https://github.com/nyjc-computing/campus.git@main
```

**Authentication issues**: Verify GitHub access for private repositories:
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
for module in auth api storage model common; do
    poetry run python -c "import campus.$module"
done
```

## Why Git Dependencies?

### vs PyPI Publishing
- ✅ **No publishing overhead** - Changes available immediately
- ✅ **Development flexibility** - Can push breaking changes without version conflicts
- ✅ **Branch-based stability** - Multiple stability levels available
- ❌ **Dependency resolution** - Slightly slower than PyPI packages

### vs Local Path Dependencies
- ✅ **External projects** - Works for projects outside Campus repo
- ✅ **External builds** - CI/CD works automatically
- ✅ **Version control** - External projects can pin specific commits
- ❌ **Network requirement** - Requires git access during install

### Migration Path
This approach provides a clear evolution:
1. **Current**: Git dependencies for active development
2. **Future**: PyPI releases for stable, mature packages
3. **Hybrid**: Git for bleeding-edge, PyPI for stability
