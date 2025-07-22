#!/usr/bin/env python3
"""Migration Test Runner - Works in container environment without database access."""

import os
import sys
import unittest
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

def detect_environment():
    """Detect testing environment."""
    has_vault = bool(os.environ.get('VAULTDB_URI'))
    has_mongo = bool(os.environ.get('MONGODB_URI'))
    
    if has_vault and has_mongo:
        return "full"
    elif has_vault:
        return "vault_only" 
    else:
        return "container"

def run_migration_tests():
    """Run migration tests appropriate for current environment."""
    env = detect_environment()
    print(f"🔍 Environment: {env}")
    print(f"   VAULTDB_URI: {'✅' if os.environ.get('VAULTDB_URI') else '❌'}")
    print(f"   MONGODB_URI: {'✅' if os.environ.get('MONGODB_URI') else '❌'}")
    print()
    
    # Load and run tests that work in container
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Test that work without database environment
    try:
        from tests.test_migration_logic import TestMigrationLogic
        suite.addTests(loader.loadTestsFromTestCase(TestMigrationLogic))
        print("✅ Loaded migration logic tests")
    except Exception as e:
        print(f"⚠️  Could not load migration logic tests: {e}")
    
    if env != "container":
        # Additional tests for environments with database access
        try:
            from tests.test_migration_vault_to_client import TestVaultMigration
            suite.addTests(loader.loadTestsFromTestCase(TestVaultMigration))
            print("✅ Loaded vault migration tests")
        except Exception as e:
            print(f"⚠️  Could not load vault tests: {e}")
    
    print()
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    print("🚀 Running migration tests...")
    print("=" * 50)
    result = runner.run(suite)
    
    # Summary
    print("=" * 50)
    print(f"📊 Results: {result.testsRun} tests")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n{'✅ Success!' if success else '❌ Some tests failed'}")
    
    return success

if __name__ == '__main__':
    success = run_migration_tests()
    sys.exit(0 if success else 1)
