# Git-Based Package Distribution Guide

## Overview

While Campus packages are still in active development, git-based dependencies provide a practical distribution method that:

- ✅ **Works immediately** - No PyPI setup required
- ✅ **Tracks development** - External projects can follow stable branches  
- ✅ **Granular control** - Use specific commits, branches, or tags
- ✅ **Real-world testing** - Validates packages work in external environments

## Distribution Strategy

### Branch Structure

**Stability Levels** (all packages together):
- `stable` - Tested, reliable versions for production use
- `dev` - Latest development with all features, daily updates
- `nightly` - Automated builds, cutting-edge but potentially unstable

**Legacy/Maintenance**:
- `campus-subpackaging` - Current development branch (will become `dev`)
- `main` - Original monorepo version (maintenance mode)

## Usage Patterns

### 1. Stable Dependencies (Recommended for Production)

```toml
# All packages from stable branch - versions guaranteed compatible
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "stable"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "stable"}
campus-suite-storage = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/storage", branch = "stable"}
```

### 2. Development Dependencies

```toml
# Latest features, updated frequently
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "dev"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "dev"}
```

### 3. Mixed Stability (Advanced)

```toml
[tool.poetry.dependencies]
# Production: Use stable for critical dependencies
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "stable"}

[tool.poetry.group.dev.dependencies]  
# Development: Use latest for testing new features
campus-suite-storage = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/storage", branch = "dev"}
```

## Installation Commands

### Poetry

```bash
# Add stable packages (recommended)
poetry add git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=stable
poetry add git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/common&branch=stable

# Add development versions
poetry add git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=dev --group dev
```

### pip

```bash
# Install stable version
pip install git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=stable

# Install specific commit (for exact reproducibility)
pip install git+https://github.com/nyjc-computing/campus.git@abc123def456#subdirectory=campus/vault
```

## External Project Templates

### Simple Vault Client

```python
# External project using stable Campus vault
# pyproject.toml
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "stable"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "stable"}

# main.py
from campus.vault import get_vault

vault = get_vault("production")
db_url = vault["database"].get("url")
```

### Full Campus Integration

```toml
[tool.poetry.dependencies]
python = "^3.11"
# All from same stability level - guaranteed compatibility
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "stable"}
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "stable"}
campus-suite-models = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/models", branch = "stable"}
campus-suite-storage = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/storage", branch = "stable"}
```

## Maintenance Workflow

### 1. Create Stability Branches

```bash
# Create stability branches from current development
git checkout campus-subpackaging

# Create stable branch (tested, production-ready)
git checkout -b stable
git push origin stable

# Create dev branch (daily updates, latest features)
git checkout -b dev  
git push origin dev

# Create nightly branch (automated builds)
git checkout -b nightly
git push origin nightly
```

### 2. Update Branches

```bash
# Weekly: Promote tested dev changes to stable
git checkout stable
git merge dev  # Only after testing
git push origin stable

# Daily: Merge latest development to dev
git checkout dev
git merge campus-subpackaging
git push origin dev

# Automated: Nightly builds from latest development
# (Done via GitHub Actions)
```

### 3. Tag Releases

```bash
# Tag major stable releases
git checkout stable
git tag v0.1.0 -m "Stable release v0.1.0 - all packages"
git push origin v0.1.0
```

## Advantages vs Alternatives

### vs PyPI Publishing
- ✅ **No publishing overhead** - Changes available immediately
- ✅ **Development flexibility** - Can push breaking changes without version conflicts
- ✅ **Branch-based stability** - Multiple stability levels available
- ❌ **Dependency resolution** - Slightly slower than PyPI packages
- ❌ **Discoverability** - Not searchable in package indexes

### vs Local Path Dependencies
- ✅ **External projects** - Works for projects outside Campus repo
- ✅ **CI/CD friendly** - External builds work automatically
- ✅ **Version control** - External projects can pin specific commits
- ❌ **Network requirement** - Requires git access during install

### vs PyPI Publishing Later
This approach provides a **migration path**:
1. **Phase 3**: Git dependencies for active development
2. **Phase 4**: PyPI releases for stable, mature packages
3. **Both**: Maintain git dependencies for bleeding-edge, PyPI for stability

## External Project Examples

### Vault-Only Project

```python
# External school management system using Campus vault
from campus.vault import get_vault
from campus.common.utils import uid

# School secrets management
vault = get_vault("school_system")
api_key = vault["external_apis"].get("student_info_system") 
db_connection = vault["databases"].get("enrollment_db")
```

### Multi-Package Integration

```python
# External analytics system using Campus models + storage
from campus.models import User, Circle
from campus.storage import get_backend
from campus.common.validation import validate_email

# Analytics integration
db = get_backend("analytics_db")
users = db.get_collection("users", User)
active_users = users.find({"last_login": {"$gte": last_week}})
```

## Next Steps

1. **Create stable branches** from current `campus-subpackaging` state
2. **Document branch policies** (what gets merged when)
3. **Set up external test project** to validate git dependencies
4. **Create workflow automation** for stable branch updates

This approach lets external projects use Campus packages **immediately** while packages mature toward eventual PyPI distribution.
