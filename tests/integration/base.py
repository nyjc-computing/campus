"""Base classes for integration tests.

This module provides reusable base classes for integration tests that handle
service manager setup, storage reset, and Flask app context management.

File: tests/integration/base.py
"""

import unittest
from typing import Any, ClassVar

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
        """Clean up service manager and reset test storage."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()


class IsolatedIntegrationTestCase(unittest.TestCase):
    """Base class for isolated integration tests with fresh Flask apps.

    This class uses shared=False to create fresh Flask apps per test class,
    ensuring complete isolation from other test classes.

    Provides:
    - Fresh service manager (shared=False)
    - Automatic storage reset and reinitialization
    - Support for tests that need custom storage initialization

    Use this when:
    - Tests need complete isolation from other test classes
    - Tests use shared state that could conflict
    - Tests modify Flask app configuration

    Example:
        class TestTracing(IsolatedIntegrationTestCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                from campus.audit.resources.traces import TracesResource
                TracesResource.init_storage()
                cls.audit_app = cls.manager.audit_app

            def setUp(self):
                super().setUp()
                # Reinitialize storage after reset
                from campus.audit.resources.traces import TracesResource
                TracesResource.init_storage()
    """

    manager: ClassVar[services.ServiceManager]

    @classmethod
    def setUpClass(cls):
        """Set up fresh service manager for isolated testing.

        Subclasses MUST call super().setUpClass() and then initialize
        any required storage resources.
        """
        cls.manager = services.create_service_manager(shared=False)
        cls.manager.setup()

    def setUp(self):
        """Reset and reinitialize storage before each test.

        Subclasses should call super().setUp() and then reinitialize
        any storage resources that were initialized in setUpClass().
        """
        # Reset storage (destroys in-memory SQLite tables)
        self.manager.reset_test_data()

        # CRITICAL: Reinitialize storage resources after reset
        # Subclasses must call super().setUp() first, then reinitialize
        # Example:
        #   super().setUp()
        #   TracesResource.init_storage()

    @classmethod
    def tearDownClass(cls):
        """Clean up service manager and reset test storage."""
        if hasattr(cls, 'manager'):
            cls.manager.reset_test_data()
            cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()


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

    def fail_dependency(self, reason: str) -> None:
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
