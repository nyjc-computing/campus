# Campus Packaging Architecture

## Overview

Campus has been restructured to support a modular, namespace-based packaging architecture that allows individual components to be distributed as separate packages while maintaining a cohesive development experience.

## Architecture Decision

### Problem Statement

The original Campus codebase had several challenges:
- Monolithic structure made it difficult to distribute individual services
- Vault service needed to be usable by external projects without pulling in all Campus dependencies
- Unclear separation between global utilities and app-specific modules
- Potential for naming conflicts between `common` and `apps/common`

### Solution: Namespace Packages

We adopted a **namespace package** approach using the `campus.*` namespace, which provides:

1. **Clean separation** of concerns
2. **Independent distribution** of packages
3. **Consistent import structure** across all packages
4. **Scalable architecture** for future growth

## Current Structure

```
campus/
├── apps/           # Web applications and API endpoints
├── common/         # Shared utilities and schemas
├── services/       # Backend services (vault, email, etc.)
└── storage/        # Storage interfaces and backends
```

### Package Responsibilities

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
- `campus.services.vault` - Secure secrets management
- `campus.services.email` - Email delivery service

#### `campus.storage`
- Database and storage abstractions
- Backend implementations (PostgreSQL, MongoDB)
- Collection and table interfaces

**Key modules:**
- `campus.storage.collections` - Document storage interface
- `campus.storage.tables` - Relational storage interface

## Migration History

### Phase 1: Namespace Creation (Completed)
- Created `campus/` namespace directory
- Moved all modules under `campus.*` namespace
- Updated all imports to use new namespace structure
- Maintained existing directory hierarchy within each namespace

### Phase 2: Structure Cleanup (Completed)
- Eliminated `campus.apps.common` to avoid confusion with `campus.common`
- Moved `campus.apps.common.{errors,models,webauth}` directly to `campus.apps.*`
- Simplified import paths and reduced namespace depth

## Import Patterns

### Recommended Import Style

```python
# Global utilities
from campus.common.utils import uid, utc_time
from campus.common import devops

# Application modules
from campus.apps.api import routes
from campus.apps.models import user
from campus.apps.errors import api_errors

# Services
from campus.services.vault import get_vault
from campus.services.email import create_email_sender

# Storage
from campus.storage import get_collection, get_table
```

### Cross-Package Dependencies

Dependency flow follows this hierarchy:
```
apps → services → storage → common
```

- `campus.apps` can import from any other package
- `campus.services` can import from `campus.storage` and `campus.common`
- `campus.storage` can import from `campus.common`
- `campus.common` should be self-contained (minimal external dependencies)

## Benefits Achieved

1. **Clear Namespace Structure**: No ambiguity between global and app-specific modules
2. **Modular Distribution**: Each package can be distributed independently
3. **Dependency Clarity**: Clear hierarchy of dependencies between packages
4. **Development Efficiency**: Single repository for coordinated development
5. **External Usability**: Services like vault can be used by external projects

## Current Status

- ✅ Namespace structure implemented
- ✅ All imports updated
- ✅ Application running successfully
- ✅ Structure cleanup completed
- 🔄 Subpackaging implementation (in progress)
