import unittest

# Set up environment variables before importing campus modules
from tests.fixtures import setup
setup.set_test_env_vars()
setup.set_vault_env_vars()

from campus.apps.api.routes import admin
from campus.models import user




class TestUsers(unittest.TestCase):

    def setUp(self):
        admin.purge_db()
        admin.init_db()

    def test_user_creation_and_activation(self):
        email = "test.user@example.com"
        user_id, _ = email.split('@')

        # Test user creation
        user_obj = user.User()
        resp = user_obj.new(email=email, name="Test User")
        self.assertIsNotNone(resp)

        # Test user activation
        user_obj.activate(email)


if __name__ == "__main__":
    unittest.main()
