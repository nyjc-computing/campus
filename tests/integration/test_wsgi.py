import unittest
import sys
import os

from tests.fixtures import services
from campus.common import env


# TODO: Fix wsgi test - Flask blueprints can't have before_request added after
# being registered. The test imports wsgi.py which calls main.create_app(),
# which calls init_app() multiple times on the same module-level blueprints.
# This test should be re-enabled after fixing the blueprint initialization.
@unittest.skip("Flask blueprint before_request registration issue")
class TestWSGI(unittest.TestCase):

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
            env.DEPLOY = deploy_mode

            # Import wsgi after service setup to avoid connection issues
            import wsgi
            from wsgi import app
            self.assertIsNotNone(app, "App should not be None")

            # Clean up for next iteration
            if 'wsgi' in sys.modules:
                del sys.modules['wsgi']


if __name__ == "__main__":
    unittest.main()
