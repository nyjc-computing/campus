import unittest
import sys
import os

from tests.fixtures import services
from campus.common import env


class TestWSGI(unittest.TestCase):
    """Test WSGI entry point with fresh Flask apps per test class.

    Previously skipped due to blueprint re-registration issues.
    Fixed by creating fresh blueprints in init_app() (Option B).
    """

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()
        # Save original environment
        cls._original_env = dict(os.environ)

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()

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
            import wsgi
            from wsgi import app
            self.assertIsNotNone(app, "App should not be None")

            # Clean up for next iteration
            if 'wsgi' in sys.modules:
                del sys.modules['wsgi']


if __name__ == "__main__":
    unittest.main()
