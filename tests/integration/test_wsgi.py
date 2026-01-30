import unittest
import sys
import os

from tests.fixtures import services
from campus.common import env


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
        # Restore environment after each test
        os.environ.clear()
        os.environ.update(self._original_env)

    def test_wsgi_import_auth(self):
        """Test campus.auth module can be imported for WSGI deployment.

        Note: Full WSGI import (import wsgi) conflicts with service_manager setup
        due to blueprint re-registration. We verify the deployment module can be
        imported instead.
        """
        env.DEPLOY = "campus.auth"
        try:
            import campus.auth
            self.assertTrue(hasattr(campus.auth, 'init_app'))
        except ImportError as e:
            self.fail(f"Failed to import campus.auth: {e}")

    def test_wsgi_import_api(self):
        """Test campus.api module can be imported for WSGI deployment.

        Note: Full WSGI import conflicts with service_manager setup due to
        shared dependencies on campus.auth (blueprint re-registration).

        TODO: campus-python library doesn't accept "testing" ENV value.
        When campus-api-python adds "testing" case, we can test full WSGI import.
        """
        env.DEPLOY = "campus.api"
        try:
            import campus.api
            self.assertTrue(hasattr(campus.api, 'init_app'))
        except ImportError as e:
            self.fail(f"Failed to import campus.api: {e}")


if __name__ == "__main__":
    unittest.main()
