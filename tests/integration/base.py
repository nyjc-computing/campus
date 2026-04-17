"""Base classes for integration tests.

This module provides reusable base classes for integration tests that handle
service manager setup, storage reset, and Flask app context management.

File: tests/integration/base.py
"""

import unittest
from typing import Any, ClassVar, NoReturn

from tests.fixtures import services


# Module-level storage for dependency check results
# This ensures persistence across test method calls
_dependency_check_results: dict[type, tuple[bool, str]] = {}


class DependencyError(RuntimeError):
    """Raised when a dependency check fails in DependencyCheckedTestCase.

    This exception indicates that a required dependency (service, resource,
    configuration) is not available, preventing tests from running.

    Unlike unittest.SkipTest, this makes dependency failures more visible
    in test output and CI/CD pipelines while still preventing dependent
    tests from running.
    """

    pass


class IntegrationTestCase(unittest.TestCase):
    """Base class for standard integration tests with service manager.

    This class provides:
    - Automatic service manager setup/teardown
    - Storage reset in setUp() for per-test isolation
    - Flask app context management
    - Proper cleanup of resources

    This is the DEFAULT base class for most integration tests.

    Example:
        class TestAssignments(IntegrationTestCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                cls.app = cls.service_manager.apps_app
                cls.user_id = UserID("test@example.com")

            def test_list_assignments(self):
                response = self.client.get('/api/v1/assignments/')
                self.assertEqual(response.status_code, 200)
    """

    service_manager: ClassVar[services.ServiceManager]
    app: ClassVar[Any]

    @classmethod
    def setUpClass(cls):
        """Set up service manager for the test class.

        Subclasses MUST call super().setUpClass() and then set cls.app to
        the appropriate Flask app (auth_app, apps_app, or audit_app).
        """
        cls.service_manager = services.create_service_manager(shared=True)
        cls.service_manager.setup()

    def setUp(self):
        """Set up test client and reset storage for per-test isolation.

        Automatically resets storage before each test to ensure tests don't
        pollute each other's state. No need for test_00_* prefixes.
        """
        if hasattr(self, 'app'):
            self.client = self.app.test_client()
            self.app_context = self.app.app_context()
            self.app_context.push()

        # Reset storage for per-test isolation
        if hasattr(self, 'service_manager'):
            self.service_manager.reset_test_data()

    def tearDown(self):
        """Clean up Flask app context after each test."""
        if hasattr(self, 'app_context'):
            self.app_context.pop()

    @classmethod
    def tearDownClass(cls):
        """Clean up service manager.

        Note: Does not call reset_test_storage() here to avoid redundant cleanup.
        The next test class will reset storage in its setup() method.
        """
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()


class IsolatedIntegrationTestCase(unittest.TestCase):
    """Base class for isolated integration tests with fresh Flask apps.

    This class uses shared=False to create fresh Flask apps per test class,
    ensuring complete isolation from other test classes.

    **UPDATED**: Now uses the new clean lifecycle API from issue #518.

    Provides:
    - Fresh service manager (shared=False)
    - Fast per-test data cleanup (preserves schema)
    - No manual Resource.init_storage() needed
    - Explicit async operation handling

    Use this when:
    - Tests need complete isolation from other test classes
    - Tests use shared state that could conflict
    - Tests modify Flask app configuration

    Example:
        class TestTracing(IsolatedIntegrationTestCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                cls.audit_app = cls.manager.audit_app

            def test_something(self):
                # No manual storage reinit needed!
                response = self.client.get('/audit/v1/traces')

    See: #518 - Proposal: Saner Integration Test Lifecycle
    """

    manager: ClassVar[services.ServiceManager]

    @classmethod
    def setUpClass(cls):
        """Set up fresh service manager for isolated testing using new API.

        Subclasses MUST call super().setUpClass() and then set cls.app/cls.audit_app
        to the appropriate Flask app.
        """
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.initialize()  # NEW API: initialize() instead of setup()

    def setUp(self):
        """Set up test client and clear data using new API.

        Uses clear_test_data() which preserves schema structure, eliminating
        the need for manual Resource.init_storage() calls.
        """
        if hasattr(self, 'manager'):
            # Clear data using new API (faster, no schema destroy)
            self.manager.clear_test_data()  # NEW API: clear_test_data() instead of reset_test_data()

    def tearDown(self):
        """Flush async operations after each test using new API."""
        if hasattr(self, 'manager'):
            self.manager.flush_async()  # NEW API: explicit async flush

    @classmethod
    def tearDownClass(cls):
        """Clean up service manager using new API."""
        if hasattr(cls, 'manager'):
            cls.manager.cleanup()  # NEW API: cleanup() instead of close()


class DependencyCheckedTestCase(unittest.TestCase):
    """Mixin for integration tests with automatic dependency checking.

    This class can be used WITH OTHER BASE CLASSES to add dependency
    checking functionality. It provides a _check_dependencies() hook
    that subclasses can override to verify required dependencies.

    If the dependency check fails, a test_000_dependencies() test will
    FAIL (making the failure visible), and all other tests will be SKIPPED.

    Example:
        class TestMyFeature(IsolatedIntegrationTestCase, DependencyCheckedTestCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                cls.manager.setup()

            def test_000_dependencies(self):
                \"\"\"Verify that required dependencies are available.\"\"\"
                if not self._verify_feature_works():
                    self.fail_dependency(
                        "Feature X is not working. See: https://github.com/user/repo/issues/123"
                    )

            def test_something(self):
                # This test will be automatically skipped if test_000_dependencies() fails
                pass
    """

    @classmethod
    def tearDownClass(cls):
        """Clean up dependency check results after test class completes."""
        # Remove this class from the dependency check results
        if cls in _dependency_check_results:
            del _dependency_check_results[cls]
        super().tearDownClass()

    def setUp(self):
        """Skip test if dependencies failed."""
        # Check module-level storage to see if dependencies failed for this test class
        test_class = self.__class__
        if test_class in _dependency_check_results:
            failed, reason = _dependency_check_results[test_class]
            if failed and self._testMethodName != "test_000_dependencies":
                self.skipTest(f"Dependencies not met: {reason}")
        super().setUp()

    def fail_dependency(self, reason: str) -> NoReturn:
        """Mark dependencies as failed, making this test fail and others skip.

        This method should be called from test_000_dependencies() when
        dependency checks fail.

        Args:
            reason: A descriptive message explaining why dependencies failed.
                    Should include issue URLs if applicable.

        Example:
            self.fail_dependency(
                "Span ingestion not working. "
                "See: https://github.com/nyjc-computing/campus/issues/459"
            )
        """
        # Store in module-level dict so other tests can see it
        test_class = self.__class__
        _dependency_check_results[test_class] = (True, reason)

        # Fail this test with clear error message
        self.fail(f"Dependency check failed: {reason}")


class CleanIntegrationTestCase(unittest.TestCase):
    """Base class for integration tests using the new clean lifecycle API.

    This class uses the new ServiceManager API from issue #518:
    - initialize() instead of setup()
    - clear_test_data() instead of reset_test_data()
    - flush_async() after each test for async operations
    - cleanup() instead of close()

    **Benefits over IntegrationTestCase**:
    - Faster per-test cleanup (clear_all_data vs reset_test_storage)
    - No manual Resource.init_storage() needed (schema preserved)
    - Explicit async operation handling
    - Clearer lifecycle ownership

    **Migration Status**: This is the new recommended base class for integration tests.
    Existing tests using IntegrationTestCase continue to work and can be migrated
    incrementally to this new base class.

    Example:
        class TestAssignments(CleanIntegrationTestCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                cls.app = cls.service_manager.apps_app
                cls.user_id = UserID("test@example.com")

            def test_list_assignments(self):
                response = self.client.get('/api/v1/assignments/')
                self.assertEqual(response.status_code, 200)

    See: #518 - Proposal: Saner Integration Test Lifecycle
    """

    service_manager: ClassVar[services.ServiceManager]
    app: ClassVar[Any]

    @classmethod
    def setUpClass(cls):
        """Set up service manager using the new API.

        Subclasses MUST call super().setUpClass() and then set cls.app to
        the appropriate Flask app (auth_app, apps_app, or audit_app).
        """
        cls.service_manager = services.create_service_manager(shared=True)
        cls.service_manager.initialize()  # NEW API: initialize() instead of setup()

    def setUp(self):
        """Set up test client and clear data for per-test isolation.

        Automatically clears data before each test using the new API.
        No need for test_00_* prefixes or manual Resource.init_storage() calls.
        """
        if hasattr(self, 'app'):
            self.client = self.app.test_client()
            self.app_context = self.app.app_context()
            self.app_context.push()

        # Clear data using new API (faster, no schema destroy)
        if hasattr(self, 'service_manager'):
            self.service_manager.clear_test_data()  # NEW API: clear_test_data() instead of reset_test_data()

    def tearDown(self):
        """Clean up Flask app context and flush async operations after each test."""
        if hasattr(self, 'app_context'):
            self.app_context.pop()

        # Flush async operations after each test
        if hasattr(self, 'service_manager'):
            self.service_manager.flush_async()  # NEW API: explicit async flush

    @classmethod
    def tearDownClass(cls):
        """Clean up service manager using the new API.

        Note: Does not call reset_test_storage() here to avoid redundant cleanup.
        The next test class will reset storage in its initialize() method.
        """
        if hasattr(cls, 'service_manager'):
            cls.service_manager.cleanup()  # NEW API: cleanup() instead of close()
