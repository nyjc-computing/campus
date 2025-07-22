# Campus Packaging Guide

## Overview

Campus has been restructured to support a modular, namespace-based packaging architecture that allows individual components to be distributed as separate packages while maintaining a cohesive development experience. This comprehensive guide covers architecture decisions, packaging strategy, distribution workflows, integration patterns, advanced operations, troubleshooting, and long-term migration plans.

**Target Audience:**
- Package maintainers managing releases and branch promotions
- DevOps contributors setting up CI/CD and automation
- External integrators using Campus packages in other projects
- Senior students learning advanced packaging concepts

---

## 1. Architecture & Design Decisions

### 1.1 Problem Statement

The original Campus codebase had several challenges:
- Monolithic structure made it difficult to distribute individual services
- Vault service needed to be usable by external projects without pulling in all Campus dependencies
- Unclear separation between global utilities and app-specific modules
- Potential for naming conflicts between `common` and `apps/common`

### 1.2 Solution: Namespace Packages

We adopted a **namespace package** approach using the `campus.*` namespace, which provides:

1. **Clean separation** of concerns
2. **Independent distribution** of packages
3. **Consistent import structure** across all packages
4. **Scalable architecture** for future growth

### 1.3 Current Structure

```
campus/
├── apps/           # Web applications and API endpoints
├── common/         # Shared utilities and schemas
├── services/       # Backend services (email, etc.)
├── storage/        # Storage interfaces and backends
└── vault/          # Secure secrets management service
```

### 1.4 Package Responsibilities

#### `campus.apps`
- Web applications (Flask apps, API routes)
- Authentication and authorization
- OAuth integrations
- User-facing interfaces

**Key modules:**
- `campus.apps.api` - REST API endpoints
- `campus.apps.oauth` - OAuth2 flows
- `campus.apps.campusauth` - Campus authentication
- `campus.apps.models` - Application data models
- `campus.apps.errors` - Application error handling

#### `campus.common`
- Shared utilities used across all packages
- Configuration and environment management
- Validation helpers
- Common schemas and types

**Key modules:**
- `campus.common.utils` - Utility functions (time, IDs, etc.)
- `campus.common.devops` - Environment configuration
- `campus.common.schema` - Shared data schemas
- `campus.common.validation` - Input validation helpers

#### `campus.services`
- Backend services that can operate independently
- Business logic that doesn't require web framework
- External service integrations

**Key modules:**
- `campus.services.email` - Email delivery service

#### `campus.vault`
- Secure secrets management service
- **Completely independent** of other campus modules to avoid circular dependencies
- Direct PostgreSQL connectivity - cannot use campus.storage since storage depends on vault
- Other services depend on vault for secrets, so vault must be self-contained

**Key modules:**
- `campus.vault.client` - Vault client management
- `campus.vault.access` - Permission and access control
- `campus.vault.db` - Direct database operations (independent of campus.storage)

#### `campus.storage`
- Database and storage abstractions
- Backend implementations (PostgreSQL, MongoDB)
- Collection and table interfaces

**Key modules:**
- `campus.storage.collections` - Document storage interface
- `campus.storage.tables` - Relational storage interface

### 1.5 Cross-Package Dependencies

Dependency flow follows this hierarchy:
```
apps → services, storage → vault → common
     ↘         ↙
      vault (for secrets)
```

**Dependency Rules:**
- `campus.apps` can import from any other package
- `campus.services` can import from `campus.storage`, `campus.vault`, and `campus.common`
- `campus.storage` can import from `campus.vault` and `campus.common` (uses vault for database secrets)
- `campus.vault` can **only** import from `campus.common` (must be independent)
- `campus.common` should be self-contained (minimal external dependencies)

**Key Constraint:** Vault must remain independent since all other modules depend on it for secrets management.

---

## 2. Distribution & Branching Strategy

### 2.1 Educational Three-Branch Model

**Branch Strategy:**
- `weekly` - Active student development, expected breakage
- `staging` - Extended testing, migration validation, pre-production
- `main` - Stable, production-ready packages for external consumption

**Migration Path:**
- Current: `campus-subpackaging` → will become `weekly`
- Legacy: Original monorepo remains in git history

### 2.2 Campus Suite Package Names

```
campus-suite-*           Import Namespace
├── campus-suite-common  → campus.common
├── campus-suite-vault   → campus.vault  
├── campus-suite-client  → campus.client
├── campus-suite-models  → campus.models
├── campus-suite-storage → campus.storage
├── campus-suite-apps    → campus.apps
└── campus-suite-workspace → campus.workspace
```

**Key Principle:** All packages from the same branch are guaranteed compatible.

### 2.3 Distribution Benefits

Git-based dependencies provide:
- ✅ **Immediate availability** - No PyPI publishing delays
- ✅ **Development tracking** - External projects follow specific branches
- ✅ **Granular control** - Pin to commits, branches, or tags
- ✅ **Real-world validation** - Test packages in external environments
- ✅ **Educational value** - Students learn industry packaging practices

### 2.4 Branch Workflow

#### Upstream Flow (Manual PRs Required)
```bash
# Feature development → weekly
git checkout weekly
git checkout -b feature/new-auth
# ... make changes, create PR: feature/new-auth → weekly

# Weekly → staging (after sprint review)
# Create PR: weekly → staging (requires review)

# Staging → main (after extended testing)
# Create PR: staging → main (requires review)
```

#### Downstream Flow (Automatic Sync)
```bash
# Changes automatically flow downstream via GitHub Actions
main → staging    # Auto-sync (no PR needed)
main → weekly     # Auto-sync (no PR needed)  
staging → weekly  # Auto-sync (no PR needed)
```

**Rationale**: Changes that passed review going upstream should automatically flow to all downstream environments without manual overhead.

---

## 3. Integration Patterns & Examples

### 3.1 Recommended Import Style

```python
# Global utilities
from campus.common.utils import uid, utc_time
from campus.common import devops

# Application modules
from campus.apps.api import routes
from campus.apps.models import user
from campus.common.errors import api_errors

# Services
from campus.vault import get_vault
from campus.services.email import create_email_sender

# Storage
from campus.storage import get_collection, get_table
```

### 3.2 Production Dependencies (Recommended)

```toml
# pyproject.toml - All packages from main branch
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "main"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "main"}
campus-suite-storage = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/storage", branch = "main"}
```

### 3.3 Pre-Production Testing

```toml
# Test upcoming releases before they hit main
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "staging"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "staging"}
```

### 3.4 Development Integration

```toml
# Latest features for development environments
[tool.poetry.group.dev.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "weekly"}
campus-suite-storage = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/storage", branch = "weekly"}
```

### 3.5 Pinned Versions (High Stability)

```toml
# Pin to specific commit for exact reproducibility
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", rev = "abc123def456"}
```

### 3.6 CLI Installation Commands

#### Poetry Integration

```bash
# Production packages
poetry add git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=main
poetry add git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/common&branch=main

# Development packages
poetry add git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=staging --group dev

# Specific commit (for reproducible builds)
poetry add git+https://github.com/nyjc-computing/campus.git@abc123def456#subdirectory=campus/vault
```

#### Direct pip Installation

```bash
# Install from main branch
pip install git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/vault&branch=main

# Install specific commit
pip install git+https://github.com/nyjc-computing/campus.git@abc123def456#subdirectory=campus/vault

# Install with extras
pip install "git+https://github.com/nyjc-computing/campus.git#subdirectory=campus/storage&branch=main[mongodb]"
```

### 3.7 Integration Examples

#### Minimal Vault Client

For projects needing only secrets management:

```toml
# pyproject.toml
[tool.poetry.dependencies]
python = "^3.11"
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "main"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "main"}
```

```python
# main.py
from campus.vault import get_vault
from campus.common.utils import uid

# External school system integration
vault = get_vault("school_system")
api_key = vault["external_apis"].get("student_info_system")
db_url = vault["databases"].get("enrollment_db")
```

#### Full Campus Integration

For comprehensive educational platform integration:

```toml
# pyproject.toml
[tool.poetry.dependencies]
python = "^3.11"
# Core packages (all from main branch for compatibility)
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/common", branch = "main"}
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/vault", branch = "main"}
campus-suite-models = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/models", branch = "main"}
campus-suite-storage = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/storage", branch = "main"}

[tool.poetry.group.dev.dependencies]
# Testing with upcoming features
campus-suite-apps = {git = "https://github.com/nyjc-computing/campus.git", subdirectory = "campus/apps", branch = "staging"}
```

```python
# app.py
from campus.models import User, Circle
from campus.storage import get_backend
from campus.vault import get_vault
from campus.common.validation import validate_email

# Multi-service integration
vault = get_vault("analytics_system")
db = get_backend("analytics_db") 
users = db.get_collection("users", User)

# Business logic
active_users = users.find({"last_login": {"$gte": last_week}})
admin_circle = Circle.get_by_name("administrators")
```

#### CI/CD Integration

For automated testing and deployment:

```yaml
# .github/workflows/test.yml
name: Test with Campus packages
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
          
      - name: Test integration
        run: |
          poetry run python -c "import campus.vault; print('✅ Vault integration works')"
          poetry run pytest tests/
```

---

## 4. Advanced Workflows & Operations

### 4.1 Cross-Branch Testing

Test upcoming features without destabilizing production dependencies:

```bash
# Test staging features in isolation
poetry add campus-suite-apps@git+https://github.com/nyjc-computing/campus.git@staging#subdirectory=campus/apps

# Run tests against staging
poetry run pytest tests/integration/ -v

# Rollback if issues found
poetry remove campus-suite-apps
poetry add campus-suite-apps@git+https://github.com/nyjc-computing/campus.git@main#subdirectory=campus/apps
```

### 4.2 Dependency Pinning Strategies

For production environments requiring stability:

```toml
# Lock to specific commits for critical dependencies
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", rev = "a1b2c3d", subdirectory = "campus/vault"}
campus-suite-common = {git = "https://github.com/nyjc-computing/campus.git", rev = "a1b2c3d", subdirectory = "campus/common"}

# Use branch dependencies for non-critical components
campus-suite-apps = {git = "https://github.com/nyjc-computing/campus.git", branch = "main", subdirectory = "campus/apps"}
```

### 4.3 Monorepo Development

For contributors working across multiple packages:

```bash
# Clone campus repository for local development
git clone https://github.com/nyjc-computing/campus.git
cd campus

# Create feature branch
git checkout -b feature/enhanced-auth
git checkout weekly  # Start from latest development

# Make changes across multiple packages
# Edit campus/vault/auth.py
# Edit campus/models/user.py  
# Edit campus/apps/api/routes/auth.py

# Test package integration locally
cd external-project
poetry add ../campus/campus/vault --editable
poetry add ../campus/campus/models --editable
poetry run pytest
```

### 4.4 Release Management

Managing package releases across the three-branch system:

```bash
# Weekly development cycle
git checkout weekly
git pull origin weekly
# Implement features, run tests

# Promote to staging for integration testing
git checkout staging
git merge weekly
git push origin staging

# After testing period, promote to main
git checkout main
git merge staging
git tag v1.2.3
git push origin main --tags
```

### 4.5 Package Compatibility Validation

Ensure cross-package compatibility during development:

```bash
# Test all packages against each other
cd /workspaces/campus

# Build and test each package
for pkg in common vault models storage client apps workspace; do
    echo "Testing campus-suite-$pkg..."
    cd campus/$pkg
    poetry install
    poetry run python -c "import campus.$pkg; print('✅ $pkg imports successfully')"
    cd ../..
done

# Test integration scenarios
poetry run python -c "
from campus.vault import get_vault
from campus.models import User
from campus.storage import get_backend
print('✅ Full integration works')
"
```

### 4.6 Automated Dependency Updates

Set up automated dependency management for external projects:

```yaml
# .github/workflows/update-dependencies.yml
name: Update Campus Dependencies
on:
  schedule:
    - cron: '0 9 * * MON'  # Weekly Monday updates
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Update to latest main
        run: |
          poetry add campus-suite-vault@git+https://github.com/nyjc-computing/campus.git@main#subdirectory=campus/vault
          poetry add campus-suite-common@git+https://github.com/nyjc-computing/campus.git@main#subdirectory=campus/common
          
      - name: Test compatibility
        run: |
          poetry run pytest tests/integration/
          
      - name: Create PR if successful
        uses: peter-evans/create-pull-request@v5
        with:
          title: "chore: Update Campus dependencies to latest main"
          body: "Automated dependency update from Campus main branch"
```

### 4.7 Multi-Project Synchronization

For organizations using Campus across multiple projects:

```bash
# Create dependency manifest for organization
cat > campus-versions.json << EOF
{
  "main": {
    "campus-suite-common": "main",
    "campus-suite-vault": "main", 
    "campus-suite-models": "main"
  },
  "staging": {
    "campus-suite-common": "staging",
    "campus-suite-vault": "staging",
    "campus-suite-models": "staging"
  }
}
EOF

# Script to update all projects
for project in project1 project2 project3; do
  cd $project
  python scripts/update_campus_deps.py --target main
  poetry install
  poetry run pytest
  cd ..
done
```

### 4.8 Security and Access Management

Configure access controls for package distribution:

```bash
# Set up SSH keys for git access
ssh-keygen -t ed25519 -C "campus-automation@school.edu"

# Configure poetry for private repositories
poetry config repositories.campus-private git@github.com:nyjc-computing/campus.git

# Use deploy keys for CI/CD
# Add public key to GitHub repo deploy keys
# Configure private key in CI environment
```

---

## 5. Troubleshooting & Maintenance

### 5.1 Common Issues and Solutions

#### Git Access Problems

```bash
# SSH key not configured
git config --global user.email "your.email@school.edu"
ssh-keygen -t ed25519 -C "your.email@school.edu"
# Add public key to GitHub account

# Repository access denied
# Verify repository URL and access permissions
git ls-remote https://github.com/nyjc-computing/campus.git
```

#### Poetry Installation Issues

```bash
# Clear poetry cache if packages fail to install
poetry cache clear pypi --all
poetry cache clear --all

# Reinstall with verbose output
poetry install -vvv

# Force reinstall specific package
poetry remove campus-suite-vault
poetry add campus-suite-vault@git+https://github.com/nyjc-computing/campus.git@main#subdirectory=campus/vault
```

#### Import Conflicts

```python
# Check package installation location
import campus.vault
print(campus.vault.__file__)

# Verify package version/branch
import campus.common
print(getattr(campus.common, '__version__', 'No version info'))
```

#### Dependency Resolution Conflicts

```bash
# Check for conflicting dependencies
poetry show --tree

# Update lock file
poetry lock --no-update

# Resolve conflicts by pinning versions
poetry add "campus-suite-vault @ git+https://github.com/nyjc-computing/campus.git@abc123#subdirectory=campus/vault"
```

### 5.2 Performance Optimization

#### Faster Installation

```bash
# Use shallow clones for faster downloads
export GIT_CLONE_PROTECTION_ACTIVE=false
poetry config installer.parallel true

# Cache git repositories locally
git config --global credential.helper store
```

#### Dependency Caching

```yaml
# GitHub Actions cache configuration
- name: Cache Poetry dependencies
  uses: actions/cache@v3
  with:
    path: |
      ~/.cache/pypoetry
      ~/.cache/pip
    key: poetry-${{ hashFiles('**/poetry.lock') }}
```

### 5.3 Development Debugging

#### Local Package Development

```bash
# Work with local editable installs
cd /path/to/campus
poetry add ./campus/vault --editable
poetry add ./campus/common --editable

# Test changes immediately
poetry run python -c "import campus.vault; print('Local changes active')"
```

#### Cross-Package Testing

```bash
# Test integration between packages
cd /workspaces/campus
python -c "
import sys
sys.path.insert(0, 'campus/vault')
sys.path.insert(0, 'campus/common') 
sys.path.insert(0, 'campus/models')

from campus.vault import get_vault
from campus.models import User
print('✅ Cross-package imports work')
"
```

### 5.4 Upgrading Git Dependencies

Systematic approach to upgrading Campus packages:

```bash
# 1. Check current versions
poetry show | grep campus-suite

# 2. Update to latest commits
poetry update campus-suite-vault campus-suite-common

# 3. Test compatibility
poetry run pytest tests/

# 4. Pin successful versions
poetry lock
```

### 5.5 Managing Breaking Changes

When Campus packages introduce breaking changes:

```bash
# Pin to last working commit
git log --oneline --grep="vault" | head -5  # Find last stable commit

# Update pyproject.toml with specific commit
[tool.poetry.dependencies]
campus-suite-vault = {git = "https://github.com/nyjc-computing/campus.git", rev = "abc123def", subdirectory = "campus/vault"}

# Test and migrate gradually
poetry install
poetry run python -c "import campus.vault; print('Pinned version works')"
```

---

## 6. Migration History & Long-Term Strategy

### 6.1 Migration History

#### Phase 1: Namespace Creation (Completed)
- Created `campus/` namespace directory
- Moved all modules under `campus.*` namespace
- Updated all imports to use new namespace structure
- Maintained existing directory hierarchy within each namespace

#### Phase 2: Structure Cleanup (Completed)
- Eliminated `campus.apps.common` to avoid confusion with `campus.common`
- Moved `campus.apps.common.{errors,models,webauth}` directly to `campus.apps.*`
- Simplified import paths and reduced namespace depth

#### Phase 3: Top-Level Package Preparation (Completed)
- Moved `campus.services.vault` to `campus.vault` for independent packaging
- Updated all import references to use new vault location
- Positioned vault as top-level package ready for distribution

### 6.2 Benefits Achieved

1. **Clear Namespace Structure**: No ambiguity between global and app-specific modules
2. **Modular Distribution**: Each package can be distributed independently
3. **Dependency Clarity**: Clear hierarchy of dependencies between packages
4. **Development Efficiency**: Single repository for coordinated development
5. **External Usability**: Services like vault can be used by external projects

### 6.3 Current Status

- ✅ Namespace structure implemented
- ✅ All imports updated
- ✅ Application running successfully
- ✅ Structure cleanup completed
- ✅ Vault positioned as top-level package
- 🔄 Subpackaging implementation (in progress)

### 6.4 Long-term Strategy

Planning for package evolution:

1. **Phase 1 (Current)**: Git dependencies for rapid development
2. **Phase 2 (6 months)**: Feature freeze and stability testing  
3. **Phase 3 (12 months)**: PyPI publishing for mature packages
4. **Phase 4 (Ongoing)**: Hybrid approach - PyPI for stable, git for experimental

This provides a clear migration path while maintaining development velocity and educational value for the NYJC Computing Department.

### 6.5 Advantages vs Alternatives

#### vs PyPI Publishing
- ✅ **No publishing overhead** - Changes available immediately
- ✅ **Development flexibility** - Can push breaking changes without version conflicts
- ✅ **Branch-based stability** - Multiple stability levels available
- ❌ **Dependency resolution** - Slightly slower than PyPI packages
- ❌ **Discoverability** - Not searchable in package indexes

#### vs Local Path Dependencies
- ✅ **External projects** - Works for projects outside Campus repo
- ✅ **CI/CD friendly** - External builds work automatically
- ✅ **Version control** - External projects can pin specific commits
- ❌ **Network requirement** - Requires git access during install

#### vs PyPI Publishing Later
This approach provides a **migration path**:
1. **Phase 3**: Git dependencies for active development
2. **Phase 4**: PyPI releases for stable, mature packages
3. **Both**: Maintain git dependencies for bleeding-edge, PyPI for stability

---

## 7. References & Related Documentation

- **CONTRIBUTING.md** - New developer onboarding and contribution workflows
- **subpackaging-plan.md** - Implementation roadmap and validation commands
- **README.md** - Project overview and quick start guide

---

*This comprehensive guide replaces and consolidates the content from `packaging-architecture.md` and `git-dependencies-guide.md`.*
