# Subpackaging Implementation Plan

## Goal

Transform the Campus monorepo into a collection of independently distributable packages while maintaining the single-repository development experience.

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
**Contents**: `campus/services/vault/`
**Dependencies**: `campus-common`, PostgreSQL drivers

```toml
[tool.poetry]
name = "campus-vault"
description = "Secure vault service for managing secrets"
dependencies = [
    "python = ^3.8"
    "campus-common = { path = "../common", develop = true }"
    "psycopg2-binary = ^2.9.0"
]
```

#### 3. `campus-storage`
**Purpose**: Storage abstractions and backends  
**Contents**: `campus/storage/`
**Dependencies**: `campus-common`, database drivers

```toml
[tool.poetry]
name = "campus-storage"
description = "Storage interfaces and backends for Campus"
dependencies = [
    "python = ^3.8"
    "campus-common = { path = "../common", develop = true }"
    "psycopg2-binary = ^2.9.0"
    "pymongo = ^4.0.0"
]
```

#### 4. `campus-apps`
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
    "campus-storage = { path = "../storage", develop = true }"
    "campus-vault = { path = "../vault", develop = true }"
    "flask = ^2.0.0"
    "requests = ^2.28.0"
]
```

## Implementation Phases

### Phase 1: Package Structure Setup

**Timeline**: 1-2 weeks

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
│   ├── vault/                           # Moved from services/vault/
│   │   ├── pyproject.toml               # campus-vault package
│   │   ├── __init__.py
│   │   └── ...
│   ├── storage/
│   │   ├── pyproject.toml               # campus-storage package
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

- [ ] All packages can be built independently
- [ ] External project successfully uses campus-vault
- [ ] CI/CD pipeline tests all packages
- [ ] Development workflow remains efficient
- [ ] Documentation covers all packages
- [ ] Packages published to PyPI
