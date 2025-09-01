"""Test runner for campus.client unit tests.

Comprehensive test runner for the campus client library unit tests, providing
isolated testing without external service dependencies.

Test Coverage:
- **tests.test_client_base**: Core HttpClient functionality (23 tests)
- **tests.test_client_vault**: Vault client library with all components (40 tests)  
- **tests.test_client_apps**: Apps service clients and resources (39 tests)
- **Total**: 102 unit tests with black-box testing methodology

Testing Philosophy:
- **No external dependencies**: All HTTP requests are mocked at the client layer
- **Black-box approach**: Tests only public interfaces, not internal implementation
- **Comprehensive coverage**: Tests cover success paths, error handling, and edge cases
- **Refactor-safe**: Tests remain stable during internal architecture changes

Usage:
    python tests/run_client_tests.py

This runner is designed for development workflows where you need fast,
reliable unit test feedback without network dependencies or service setup.
"""

import os
import sys
import unittest

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_client_tests():
    """Run all client unit tests."""
    print("Running Campus Client Unit Tests...")
    print("=" * 50)

    # Create test suite with only client tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add client test modules
    test_modules = [
        'tests.test_client_base',
        'tests.test_client_vault',
        'tests.test_client_apps'
    ]

    for module_name in test_modules:
        try:
            module_suite = loader.loadTestsFromName(module_name)
            suite.addTest(module_suite)
            print(f"✓ Loaded tests from {module_name}")
        except Exception as e:
            print(f"✗ Failed to load {module_name}: {e}")

    print("-" * 50)

    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    print("-" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(
        f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")

    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")

    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")

    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nResult: {'PASSED' if success else 'FAILED'}")

    return success


if __name__ == "__main__":
    success = run_client_tests()
    sys.exit(0 if success else 1)
