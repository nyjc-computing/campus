import unittest
from campus.apps import api


class TestUsers(unittest.TestCase):

    def setUp(self):
        api.purge()
        api.init_db()

    def test_user_creation_and_activation(self):
        email = "test.user@example.com"
        user_id, _ = email.split('@')

        # Test user creation
        resp = api.users.new(email=email, name="Test User")
        self.assertEqual(resp.status, "ok", f"Failed to create user: {resp.message}, Response data: {resp.data}")

        # Test user activation
        resp = api.users.activate(email)
        self.assertEqual(resp.status, "ok", f"Failed to activate user: {resp.message}, Response data: {resp.data}")

if __name__ == "__main__":
    unittest.main()