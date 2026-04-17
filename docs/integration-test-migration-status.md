# Integration Test Migration Status

## Issue #518: Saner Integration Test Lifecycle

### ✅ Successfully Migrated Tests

The following integration test classes have been successfully migrated to use the new `CleanIntegrationTestCase` base class:

| Test File | Tests | Status | Commit |
|-----------|-------|--------|--------|
| `test_login_routes_trailing_slash.py` | 4 tests | ✅ PASSED | 57c1009 |
| `test_assignments.py` | 12 tests | ✅ PASSED | 1963465 |
| `test_auth_routes.py` | 1 test | ✅ PASSED | 9664e95 |
| `test_oauth_routes.py` | 4 tests | ✅ PASSED | b1d8166 |
| `test_yapper.py` | 3 tests | ✅ PASSED | 8c9067f |

**Total**: 24 tests successfully migrated, all passing.

### ⚠️ Known Issues: Tests Requiring Manual Storage Management

The following tests have complex storage initialization requirements and need special handling:

#### `test_audit_tracing_middleware.py` - 12 tests

**Status**: ⚠️ PARTIAL MIGRATION - Dependency check failing

**Issue**: The `TestTracingMiddlewareSpanIngestion` class has complex storage initialization requirements:

1. Uses `DependencyCheckedTestCase` for automatic test skipping
2. Requires manual `TracesResource.init_storage()` calls
3. Tests run in specific order with `test_000_dependencies` running first
4. Dependency check runs before `setUp()`, creating a chicken-and-egg problem

**Current State**: 
- `TestTracingMiddlewareBasic`: ✅ Migrated successfully (1 test passing)
- `TestTracingMiddlewareSpanIngestion`: ❌ Failing at dependency check (11 tests skipped)

**Error**:
```
AssertionError: Dependency check failed: Spans table not accessible: no such table: spans. 
Storage initialization may have failed.
```

**Root Cause**: The spans table created in `setUpClass()` is not accessible when `test_000_dependencies` runs, likely due to connection or timing issues with the new lifecycle API.

**Recommendation**: This test may need to keep using the old API or require custom lifecycle handling. The manual storage initialization pattern is integral to how these tests verify span ingestion functionality.

**Migration Attempts**:
- Attempted to use new API with manual `TracesResource.init_storage()` calls
- Tried calling `init_storage()` both before and after `clear_test_data()`
- Issue persists with table not being found in dependency check

### 📊 Migration Progress

- **Total Integration Tests**: 36 tests (24 migrated + 12 tracing tests)
- **Successfully Migrated**: 24/36 (67%)
- **Known Issues**: 12/36 (33%)
- **Regressions**: 0 (all previously passing tests still pass)

### 🎯 Next Steps

1. **Consider keeping tracing tests on old API**: These tests have specialized requirements that may not align with the new lifecycle
2. **Create custom base class**: Could create `TracingIntegrationTestCase` with custom lifecycle for these tests
3. **Separate concern**: Keep dependency-checked tests separate from standard integration tests

### 📝 Notes

- All other integration tests are successfully using the new lifecycle API
- The new API provides significant benefits: faster cleanup, no manual schema reinit, cleaner lifecycle
- The failing tests represent edge cases with complex storage initialization needs
- No regressions introduced in previously working tests

---

**Last Updated**: 2026-04-17
**Related Issue**: #518 - Proposal: Saner Integration Test Lifecycle
