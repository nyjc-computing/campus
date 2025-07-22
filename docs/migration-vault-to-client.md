# Migration: campus.vault → campus.client

## Overview

This document tracks the migration from direct `campus.vault` imports to HTTP-based `campus.client.vault` access. The goal is to eliminate direct database dependencies and improve service isolation.

## Migration Goal

**FROM**: Direct vault database access
```python
from campus.vault import get_vault
vault = get_vault("storage")
secret = vault.get("MONGODB_URI")
```

**TO**: HTTP-based client access
```python
import campus.client.vault as vault
secret = vault["storage"].get("MONGODB_URI")
```

## Benefits

1. **Service Isolation**: Applications no longer need direct VAULTDB_URI access
2. **Deployment Flexibility**: Vault service can be deployed independently
3. **Security**: Centralized authentication and permission management
4. **Scalability**: HTTP-based access allows for load balancing and caching

## Progress Status

### ✅ Phase 1: Client Architecture (COMPLETED)
- **campus.client.vault module**: Fully functional and validated
- **API alignment**: Client-server API calls 100% aligned
- **Test validation**: Client making real HTTP requests successfully
- **Documentation**: Complete API reference available

### ✅ Phase 2: Test Infrastructure (COMPLETED)  
- **Import structure tests**: All passing
- **Flask dependency**: Resolved
- **Collections→documents rename**: Updated across codebase
- **Error reduction**: From 5 infrastructure errors to 3 service-level issues

### 🔄 Phase 3: Production Migration (IN PROGRESS)

**Status**: ~25% Complete

#### Files Requiring Migration (10 total):

| File | Status | Import Pattern | Usage Pattern |
|------|--------|---------------|---------------|
| `campus/workspace/__init__.py` | ⏳ Pending | `import campus.vault as vault` | Direct module access |
| `campus/apps/api/routes/clients.py` | ⏳ Pending | `from campus.vault import client` | Client management |
| `campus/apps/api/__init__.py` | ⏳ Pending | `from campus.vault import client` | Client management |
| `campus/apps/campusauth/authentication.py` | ⏳ Pending | `from campus.vault import client` | Client management |
| `campus/apps/campusauth/context.py` | ⏳ Pending | `from campus.vault.client import ClientResource` | Resource access |
| `campus/apps/oauth/google.py` | ⏳ Pending | `from campus.vault import get_vault` | Vault access |
| `campus/apps/__init__.py` | ⏳ Pending | `from campus.vault import Vault` | Vault class |
| `campus/services/email/smtp.py` | ⏳ Pending | `from campus.vault import get_vault` | Vault access |
| `campus/storage/documents/backend/mongodb.py` | ⏳ Pending | `from campus.vault import get_vault` | Vault access |
| `campus/storage/tables/backend/postgres.py` | ⏳ Pending | `from campus.vault import get_vault` | Vault access |

#### Migration Patterns

**Pattern 1: Vault Access (`get_vault`)**
```python
# BEFORE
from campus.vault import get_vault
storage_vault = get_vault("storage")
uri = storage_vault.get("MONGODB_URI")

# AFTER
import campus.client.vault as vault
uri = vault["storage"].get("MONGODB_URI")
```

**Pattern 2: Client Management**
```python
# BEFORE
from campus.vault import client
client_resource = client.create_client(name, description)

# AFTER
import campus.client.vault as vault
client_resource = vault.client.new(name, description)
```

**Pattern 3: Direct Vault Class**
```python
# BEFORE
from campus.vault import Vault
vault_instance = Vault(label)

# AFTER
import campus.client.vault as vault
# Use vault[label] interface instead
```

## Authentication

**Current Assumption**: All services have access to `CLIENT_ID` and `CLIENT_SECRET` environment variables.

**Migration Impact**: No authentication code changes required. The client automatically loads credentials from environment variables.

**Future Work**: API key-based authentication for services that cannot use environment variables.

## Dependencies

### Package Dependencies That Will Change

**campus.storage**: Currently depends on `campus-suite-vault` (direct dependency)
- **After migration**: Will depend on `campus-suite-client` (HTTP dependency)
- **Impact**: Remove direct vault dependency, add client dependency

**Other packages**: Similar pattern for any package currently importing `campus.vault`

## Validation Plan

1. **Per-file migration**: Update imports and usage patterns
2. **Functionality testing**: Ensure identical behavior with client vs direct access
3. **Integration testing**: Verify service-to-service communication works
4. **Performance testing**: Measure HTTP overhead vs direct database access

## Rollback Plan

Since client architecture is proven functional:
- **Low risk**: HTTP client has been validated against real vault service
- **Rollback method**: Revert import statements and usage patterns
- **No database changes**: Migration is purely code-level

## Next Steps

1. **Choose migration order**: Start with least critical files
2. **File-by-file migration**: Update imports and usage patterns
3. **Test each migration**: Verify functionality preserved
4. **Update dependencies**: Remove direct vault dependencies from package files
5. **Final validation**: Full integration testing

---

*Last updated: July 22, 2025*
*Migration status: ~25% complete*
