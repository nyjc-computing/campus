"""Base classes for integration tests.

This module provides reusable base classes for integration tests that need
dependency checking and automatic test skipping.

File: tests/integration/base.py
"""

import unittest
from typing import ClassVar

from tests.fixtures import services


class DependencyCheckedTestCase(unittest.TestCase):
    """Base class for integration tests with automatic dependency checking.

    Subclasses can override the `_check_dependencies()` classmethod to verify
    that required dependencies are available before running tests. If the check
    fails, the entire test class is automatically skipped.

    Example:
        class TestMyFeature(DependencyCheckedTestCase):
            @classmethod
            def setUpClass(cls):
                super().setUpClass()
                cls.manager = services.create_service_manager(shared=False)
                cls.manager.setup()

            @classmethod
            def _check_dependencies(cls):
                \"\"\"Verify that required dependencies are available.\"\"\"
                # Perform dependency check here
                # If check fails, call cls._skip_dependency() with a reason
                # Example:
                if not cls._verify_feature_works():
                    cls._skip_dependency(
                        "Feature X is not working. See: https://github.com/user/repo/issues/123"
                    )

            def test_something(self):
                # This test will be automatically skipped if _check_dependencies() fails
                pass
    """

    manager: ClassVar[services.ServiceManager]

    @classmethod
    def setUpClass(cls):
        """Set up the test class and check dependencies.

        This method:
        1. Calls subclass setup (if they override and call super())
        2. Runs dependency checks via _check_dependencies()
        3. Skips all tests if dependencies are not met

        Subclasses that override setUpClass MUST call super().setUpClass()
        after their own setup logic.
        """
        # Perform dependency checks
        try:
            cls._check_dependencies()
        except unittest.SkipTest:
            # Re-raise SkipTest to skip the entire class
            raise

    @classmethod
    def _check_dependencies(cls) -> None:
        """Check that required dependencies are available.

        Subclasses should override this method to perform their dependency checks.
        If a dependency check fails, call `_skip_dependency()` with a descriptive
        reason.

        Default implementation does nothing (no dependencies).
        """
        pass

    @classmethod
    def _skip_dependency(cls, reason: str) -> None:
        """Skip the entire test class due to failed dependency check.

        Args:
            reason: A descriptive message explaining why the tests are being skipped.
                    Should include issue URLs if applicable.

        Example:
            cls._skip_dependency(
                "Span ingestion not working. "
                "See: https://github.com/user/repo/issues/459"
            )
        """
        raise unittest.SkipTest(reason)

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class.

        Subclasses that override tearDownClass MUST call super().tearDownClass().
        """
        # Reset test data and close services if manager was initialized
        if hasattr(cls, 'manager'):
            cls.manager.reset_test_data()
            cls.manager.close()
            import campus.storage.testing
            campus.storage.testing.reset_test_storage()
