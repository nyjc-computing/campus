import unittest

from tests.fixtures import services


class TestUsers(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()

        # Import after service setup to avoid connection issues
        from campus.apps.api.routes import admin
        from campus.models import user

        cls.admin = admin
        cls.user = user

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()

    def setUp(self):
        # Initialize the database for each test
        self.admin.purge_db()
        self.admin.init_db()

    def test_user_creation_and_activation(self):
        email = "test.user@example.com"
        user_id, _ = email.split('@')

        # Test user creation
        user_obj = self.user.User()
        resp = user_obj.new(email=email, name="Test User")
        self.assertIsNotNone(resp)

        # Test user activation
        user_obj.activate(email)


if __name__ == "__main__":
    unittest.main()
