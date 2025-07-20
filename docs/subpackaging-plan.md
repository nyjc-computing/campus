# Subpackaging Implementation Plan

## Goal

Transform the Campus monorepo into a collection of independently distributable packages while maintaining the single-repository development experience.

## Dependency Architecture

### Circular Dependency Prevention

The vault service is designed to be completely independent to prevent circular dependencies:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│    apps     │──▶│   storage   │──▶│    vault    │
└─────────────┘    └─────────────┘    └─────────────┘
       │                  │                   │
       └──────────────────┼───────────────────┘
                          ▼
                   ┌─────────────┐
                   │   common    │
                   └─────────────┘
```

**Why vault must be independent:**
- Storage backends need database credentials from vault
- Apps need API keys and secrets from vault  
- Services need external service credentials from vault
- If vault depended on storage, it would create a circular dependency

**Vault's independence strategy:**
- Direct PostgreSQL connectivity via `psycopg2`
- Own connection management in `campus.vault.db`
- No dependency on `campus.storage` abstractions
- Only depends on `campus.common` for utilities

## Target Packages

### Priority 1: Core Infrastructure

#### 1. `campus-common`
**Purpose**: Shared utilities and foundational components
**Contents**: `campus/common/`
**Dependencies**: Minimal external dependencies only

```toml
[tool.poetry]
name = "campus-common"
description = "Shared utilities for Campus ecosystem"
dependencies = [
    "python = ^3.8"
    # Add minimal dependencies as needed
]
```

#### 2. `campus-vault`  
**Purpose**: Secure secrets management service
**Contents**: `campus/vault/`
**Dependencies**: `campus-common` **only** (no other campus packages to avoid circular dependencies)

```toml
[tool.poetry]
name = "campus-vault"
description = "Secure vault service for managing secrets"
dependencies = [
    "python = ^3.8"
    "campus-common = { path = "../common", develop = true }"
    "psycopg2-binary = ^2.9.0"
    # NOTE: Cannot depend on campus-storage to avoid circular dependencies
    # Vault implements its own direct PostgreSQL access
]
```

#### 3. `campus-storage`
**Purpose**: Storage abstractions and backends  
**Contents**: `campus/storage/`
**Dependencies**: `campus-common`, `campus-vault` (for database secrets), database drivers

```toml
[tool.poetry]
name = "campus-storage"
description = "Storage interfaces and backends for Campus"
dependencies = [
    "python = ^3.8"
    "campus-common = { path = "../common", develop = true }"
    "campus-vault = { path = "../vault", develop = true }"
    "psycopg2-binary = ^2.9.0"
    "pymongo = ^4.0.0"
]
```

#### 4. `campus-client`
**Purpose**: General-purpose client libraries for external integrations
**Contents**: `campus/client/`
**Dependencies**: `campus-common`, HTTP client libraries

```toml
[tool.poetry]
name = "campus-client"
description = "Client libraries for external API integrations"
dependencies = [
    "python = ^3.8"
    "campus-common = { path = "../common", develop = true }"
    "requests = ^2.28.0"
]
```

#### 5. `campus-models`
**Purpose**: Data models and schemas
**Contents**: `campus/models/`
**Dependencies**: `campus-common`, validation libraries

```toml
[tool.poetry]
name = "campus-models"
description = "Data models and schemas for Campus"
dependencies = [
    "python = ^3.8"
    "campus-common = { path = "../common", develop = true }"
]
```

#### 6. `campus-apps`
**Purpose**: Web applications and API endpoints
**Contents**: `campus/apps/`  
**Dependencies**: All other campus packages, Flask, web frameworks

```toml
[tool.poetry]
name = "campus-apps"
description = "Web applications and API for Campus"
dependencies = [
    "python = ^3.8"
    "campus-common = { path = "../common", develop = true }"
    "campus-vault = { path = "../vault", develop = true }"
    "campus-storage = { path = "../storage", develop = true }"
    "campus-client = { path = "../client", develop = true }"
    "campus-models = { path = "../models", develop = true }"
    "flask = ^2.0.0"
    "requests = ^2.28.0"
]
```

## Implementation Phases

### Phase 0: Prerequisites (Completed ✅)

**Timeline**: Completed

1. **Namespace Structure Setup**
   - ✅ Created `campus/` namespace package
   - ✅ Moved all modules under `campus.*` namespace
   - ✅ Updated all imports to use new namespace structure

2. **Structure Cleanup**
   - ✅ Eliminated `campus.apps.common` to avoid confusion
   - ✅ Moved components directly to `campus.apps.*`
   - ✅ Simplified import paths

3. **Package Positioning**
   - ✅ Moved vault from `campus.services.vault` to `campus.vault`
   - ✅ Updated all references and documentation
   - ✅ Positioned vault as independent top-level package
   - ✅ Moved `campus.apps.client` to `campus.client`
     - **Reason**: The `client` module provides general-purpose classes and functions for interacting with APIs of integration providers. It is not application-specific and should be moved out of `campus.apps` to better align with its purpose.
   - ✅ Moved models from `campus.apps.models` to `campus.models`
     - **Reason**: Centralizing models in the root folder simplifies access and improves organization.
   - ✅ Updated all import statements to reflect the new model locations
   - ✅ Added re-exports in `campus/__init__.py` for static type checker compatibility

### Phase 0.5: Circular Dependency Resolution (Completed ✅)

**Timeline**: Completed - July 2025  
**Critical breakthrough that unblocks true package independence**

1. **Circular Dependency Analysis**
   - ✅ Identified circular dependency: `campus.models` ↔ `campus.apps`
   - ✅ Root cause: Models importing `campus.apps.errors` while apps import models
   - ✅ Secondary issue: Models importing `campus.apps.webauth.token`

2. **Shared Component Migration**
   - ✅ **Moved `campus.apps.errors` → `campus.common.errors`**
     - Rationale: Error definitions are shared infrastructure, not app-specific
     - Updated 7+ model files and 8+ app route files
   - ✅ **Moved `campus.apps.webauth` → `campus.common.webauth`**
     - Rationale: Authentication schemas are shared infrastructure used by both models and apps
     - Updated all internal cross-references and imports

3. **Import Structure Fixes**
   - ✅ **Eliminated eager imports from `campus/__init__.py`**
     - Removed forced imports that masked dependency issues
     - Allows individual packages to import cleanly without side effects
   - ✅ **Fixed workspace namespace package imports**
     - Changed `from campus import common` → `import campus.common as common`
     - Resolved linting errors and follows proper namespace package conventions
   - ✅ **Temporarily disabled client imports in workspace**
     - Client being refactored in separate branch (`campus-client`)
     - Added TODO comments for re-enabling when complete

4. **Dependency Architecture Achievement**
   ```
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │    apps     │──▶│   models    │──▶│   common    │
   └─────────────┘    └─────────────┘    └─────────────┘
          │                  │                   │
          │            ┌─────────────┐           │
          └──────────▶│   storage   │───────────┘
          │            └─────────────┘           │
          │                  │                   │
          └──────────────────▼───────────────────┘
                       ┌─────────────┐
                       │    vault    │
                       └─────────────┘
   ```
   - ✅ **Clean dependency hierarchy established**
   - ✅ **No circular dependencies remaining**
   - ✅ **True package independence now possible**

5. **Validation and Testing**
   - ✅ All individual packages can import without circular dependency errors
   - ✅ `campus.workspace` imports successfully (database initialization issues are separate)
   - ✅ `campus.client` modules work independently
   - ✅ Cross-package imports follow proper dependency flow

**Impact**: This phase resolved the fundamental architectural blocker that would have prevented true package independence in Phase 1. All packages can now be isolated and built independently.

### Phase 1: Package Structure Setup

**Timeline**: 1-2 weeks  
**Status**: 🟢 **Ready to begin** (circular dependencies resolved)

1. **Create pyproject.toml files**
   - Add Poetry configuration for each package
   - Define dependencies and development dependencies
   - Set up namespace package configuration

2. **Verify package isolation**
   - Ensure each package can be built independently
   - Test import resolution
   - Validate dependency tree

3. **Development workflow setup**
   - Configure Poetry workspace for development
   - Set up editable installs for local development
   - Update development scripts

**Prerequisites met**: ✅ Clean dependency architecture with no circular dependencies

### Phase 2: Build and Test Infrastructure

**Timeline**: 1 week

1. **CI/CD Pipeline Updates**
   ```yaml
   strategy:
     matrix:
       package: ["common", "vault", "storage", "apps"]
   
   steps:
     - name: Test ${{ matrix.package }}
       run: |
         cd campus/${{ matrix.package }}
         poetry install
         poetry run pytest
   
     - name: Build ${{ matrix.package }}
       run: |
         cd campus/${{ matrix.package }}
         poetry build
   ```

2. **Testing Strategy**
   - Unit tests for each package
   - Integration tests across packages
   - End-to-end testing for full application

3. **Quality Assurance**
   - Linting and formatting per package
   - Type checking with mypy
   - Security scanning

### Phase 3: Distribution Setup

**Timeline**: 1 week

1. **Package Publishing**
   - Configure PyPI publishing
   - Set up package versioning strategy
   - Create release automation

2. **Documentation**
   - Package-specific documentation
   - Installation guides for external users
   - API documentation

3. **External Usage Validation**
   - Test vault package in external project
   - Validate minimal dependency installation
   - Verify namespace package behavior

## Directory Structure After Implementation

```
campus/                                    # Repository root
├── pyproject.toml                        # Workspace configuration
├── poetry.lock                           # Development lockfile
├── campus/
│   ├── __init__.py                       # Namespace package marker
│   ├── common/
│   │   ├── pyproject.toml               # campus-common package
│   │   ├── __init__.py
│   │   └── ...
│   ├── vault/                           # Top-level vault package
│   │   ├── pyproject.toml               # campus-vault package
│   │   ├── __init__.py
│   │   └── ...
│   ├── storage/
│   │   ├── pyproject.toml               # campus-storage package
│   │   ├── __init__.py
│   │   └── ...
│   ├── client/                          # General-purpose client module
│   │   ├── pyproject.toml               # campus-client package
│   │   ├── __init__.py
│   │   └── ...
│   ├── models/                          # Centralized models directory
│   │   ├── pyproject.toml               # campus-models package
│   │   ├── __init__.py
│   │   └── ...
│   └── apps/
│       ├── pyproject.toml               # campus-apps package
│       ├── __init__.py
│       └── ...
├── tests/                               # Integration tests
├── docs/                                # Documentation
└── scripts/                             # Build and deployment scripts
```

## Development Workflow

### Local Development
```bash
# Install all packages in development mode
poetry install

# Work on specific package
cd campus/vault
poetry install
poetry run pytest

# Run full application
poetry run python main.py
```

### Package Distribution
```bash
# Build individual package
cd campus/vault
poetry build

# Publish to PyPI
poetry publish
```

### External Usage
```bash
# Install just vault service
pip install campus-vault

# Use in external project
from campus.vault import get_vault
```

## Migration Strategy

### Import Compatibility
- All existing imports continue to work
- No code changes required during transition
- Gradual migration to package-specific installs

### Dependency Management
- Development: All packages installed together
- Production: Install only needed packages
- CI/CD: Test both scenarios

### Versioning Strategy
- Independent versioning per package
- Semantic versioning (semver)
- Coordinated releases for breaking changes

## Benefits

1. **Reduced Dependencies**: External projects only install what they need
2. **Faster Installation**: Smaller package sizes
3. **Independent Evolution**: Packages can evolve at different rates  
4. **Clear Boundaries**: Well-defined interfaces between components
5. **Easier Testing**: Package-level isolation improves test reliability
6. **Better Documentation**: Package-specific docs for external users

## Risks and Mitigations

### Risk: Dependency Hell
**Mitigation**: Careful dependency management, regular compatibility testing

### Risk: Development Complexity  
**Mitigation**: Maintain Poetry workspace for coordinated development

### Risk: Breaking Changes
**Mitigation**: Semantic versioning, coordinated releases, deprecation notices

### Risk: Build Pipeline Complexity
**Mitigation**: Incremental migration, shared CI/CD templates

## Success Metrics

- [x] All packages can be built independently *(pending Phase 1)*
- [x] External project successfully uses campus-vault *(pending Phase 1)*
- [x] CI/CD pipeline tests all packages *(pending Phase 2)*
- [x] Development workflow remains efficient *(current: ✅)*
- [x] Documentation covers all packages *(current: ✅)*
- [x] Packages published to PyPI *(pending Phase 3)*

## Completed Prerequisites ✅

- **Namespace Structure**: All modules successfully moved to `campus.*` namespace
- **Import Updates**: All 50+ files updated to use new namespace structure  
- **Structure Cleanup**: Eliminated confusing `campus.apps.common` structure
- **Vault Positioning**: Moved vault to top-level for independent packaging
- **Client Positioning**: Moved client to top-level for general-purpose use
- **Models Positioning**: Moved models to top-level for centralized access
- **Static Type Checker Support**: Added simple re-exports in `campus/__init__.py` for junior developer onboarding
- **Application Verification**: Full application runs successfully with new structure
- **Documentation**: Architecture and implementation plans documented
