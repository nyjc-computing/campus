import os
import sys
import unittest

from campus.common import env
from tests.fixtures import services


class TestWSGI(unittest.TestCase):
    """Test WSGI entry point with fresh Flask apps per test class.

    NOTE: This test does NOT use IntegrationTestCase base class because:
    - It requires custom environment variable management (saving/restoring os.environ)
    - It needs special module cleanup (deleting 'wsgi' from sys.modules)
    - It tests deployment-specific behavior that differs from standard integration tests

    Previously skipped due to blueprint re-registration issues.
    Fixed by creating fresh blueprints in init_app() (Option B).
    """

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.initialize()
        # Save original environment
        cls._original_env = dict(os.environ)

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.cleanup()

        # Reset test storage to clear SQLite in-memory database
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def tearDown(self):
        # Clean up wsgi module imports
        if 'wsgi' in sys.modules:
            del sys.modules['wsgi']

    def test_wsgi_import(self):
        for deploy_mode in ("campus.api", "campus.auth"):
            env.set('DEPLOY', deploy_mode)

            # Import wsgi after service setup to avoid connection issues
            from wsgi import app
            self.assertIsNotNone(app, "App should not be None")

            # Clean up for next iteration
            if 'wsgi' in sys.modules:
                del sys.modules['wsgi']

    def test_boot_names_the_process_journey(self):
        """create_app names the boot journey (#114): the worker's
        startup SDK calls join one journey per boot, and journey cards
        render "campus.<service>.boot" instead of a raw id."""
        from campus_python import tracing

        tracing._reset_process_journey()
        self.addCleanup(tracing._reset_process_journey)

        env.set('DEPLOY', 'campus.api')
        from wsgi import app
        self.assertIsNotNone(app, "App should not be None")

        headers = tracing.propagation_headers()
        self.assertEqual(
            headers.get(tracing.JOURNEY_NAME_HEADER), "campus.api.boot"
        )
        self.assertTrue(
            headers.get(tracing.JOURNEY_ID_HEADER, "").startswith("uid-journey-")
        )


if __name__ == "__main__":
    unittest.main()
