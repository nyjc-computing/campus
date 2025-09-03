import unittest
import os
import sys

from tests.fixtures import services


class TestWSGI(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()

    def setUp(self):
        # Clean up wsgi module imports at start of each test
        if 'wsgi' in sys.modules:
            del sys.modules['wsgi']

    def tearDown(self):
        # Clean up wsgi module imports
        if 'wsgi' in sys.modules:
            del sys.modules['wsgi']

    def test_wsgi_import(self):
        for deploy_mode in ("apps", "vault"):
            os.environ["DEPLOY"] = deploy_mode

            # Import wsgi after service setup to avoid connection issues
            import wsgi
            from wsgi import app
            self.assertIsNotNone(app, "App should not be None")

            # Clean up for next iteration
            if 'wsgi' in sys.modules:
                del sys.modules['wsgi']


if __name__ == "__main__":
    unittest.main()
