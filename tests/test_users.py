import unittest
from apps import palmtree


class TestUsers(unittest.TestCase):

    def setUp(self):
        palmtree.purge()
        palmtree.init_db()

    def test_user_creation_and_activation(self):
        email = "test.user@example.com"
        user_id, _ = email.split('@')

        # Test user creation
        resp = palmtree.users.new(email, "Test User")
        self.assertEqual(resp.status, "ok", f"Failed to create user: {resp.message}, Response data: {resp.data}")

        # Test user activation
        resp = palmtree.users.activate(email)
        self.assertEqual(resp.status, "ok", f"Failed to activate user: {resp.message}, Response data: {resp.data}")

if __name__ == "__main__":
    unittest.main()