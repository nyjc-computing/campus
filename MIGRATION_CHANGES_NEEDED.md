# Migration Changes Needed

## Summary of Issues Found

### 1. Collections → Documents Rename
**Files needing updates:**
- `tests/test_migration_vault_to_client.py` (2 locations)
- `tests/test_migration_logic.py` (1 location)  
- `tests/test_specific_component_migrations.py` (2 locations)
- `docs/PACKAGING.md` (1 location)
- `campus/storage/pyproject.toml` (description)
- `campus/storage/errors.py` (comment)
- `.github/workflows/package-testing.yml` (comments)

**Import changes needed:** 
```python
# OLD:
from campus.storage.collections.backend.mongodb import _get_mongodb_uri

# NEW: 
from campus.storage.documents.backend.mongodb import _get_mongodb_uri
```

**Documentation/comment changes:**
- Update all references from "collections" to "documents" in storage context
- Update package descriptions and comments
- Update workflow documentation

### 2. Missing Flask Dependency
**Issue:** Tests failing with `ModuleNotFoundError: No module named 'flask'`
**Location:** `campus/vault/__init__.py` line 76
**Solution:** Install Flask or mock the imports in tests

### 3. Campus.vault Import Issues  
**Issue:** `AttributeError: module 'campus' has no attribute 'vault'`
**Root cause:** Tests trying to patch `campus.vault.db.get_connection` but module not importable
**Affected tests:** 5 test methods

### 4. Legacy campus.vault Direct Imports (Migration Targets)
**Files with direct vault imports that need migration:**
- `campus/apps/api/routes/clients.py`
- `campus/apps/api/__init__.py` 
- `campus/apps/campusauth/authentication.py`
- `campus/apps/campusauth/context.py`
- `campus/workspace/__init__.py`
- `campus/apps/oauth/google.py`
- `campus/apps/__init__.py`
- `campus/services/email/smtp.py`
- `campus/storage/documents/backend/mongodb.py`
- `campus/storage/tables/backend/postgres.py`

### 5. Test Environment Setup
**Current environment:** `vault_only` (VAULTDB_URI=✅, MONGODB_URI=❌)
**Test issues:** 5 errors, 0 failures
**Import structure tests:** ✅ All passing

## Recommended Plan

### Phase 1: Fix Test Infrastructure (Immediate)
1. ✅ Update collections → documents imports in tests
2. ✅ Install Flask or mock Flask imports 
3. ✅ Fix vault module import issues in tests

### Phase 2: Validate Current Architecture (Next)  
1. Get all 14 tests passing
2. Validate client architecture works end-to-end
3. Document current functionality gaps

### Phase 3: Legacy Migration (Future)
1. Migrate direct vault imports to campus.client
2. Eliminate VAULTDB_URI dependencies from apps
3. Final validation without database environment variables

## Current Status
- ✅ Client architecture complete and functional
- ✅ Import structure tests all passing  
- 🔄 Test infrastructure needs fixes
- ⏳ Legacy migration implementation pending
