import unittest
from apps import api


class TestClients(unittest.TestCase):

    def setUp(self):
        api.purge()
        api.init_db()

    def test_client_creation_and_admin_management(self):
        data = {
            "name": "Test Client",
            "description": "A test client.",
            "admins": ["admin1@example.com"]
        }
        resp = api.clients.new(**data)
        self.assertEqual(resp.status, "ok", f"Failed to create client: {resp.message}, Response data: {resp.data}")
        client_id = resp.data['id']

        # Test adding an admin
        resp = api.clients.admins.add(client_id, "admin2@example.com")
        self.assertEqual(resp.status, "ok", f"Failed to add admin: {resp.message}, Response data: {resp.data}")

        # Test removing an admin
        resp = api.clients.admins.remove(client_id, "admin2@example.com")
        self.assertEqual(resp.status, "ok", f"Failed to remove admin: {resp.message}, Response data: {resp.data}")

    def test_validating_credentials(self):
        data = {
            "name": "Test Client",
            "description": "A test client.",
            "admins": ["admin1@example.com"]
        }
        resp = api.clients.new(**data)
        client_id = resp.data['id']
        secret_hash = api.clients.replace(client_id).data

        # Test credential validation
        is_valid = api.clients.validate_credentials(client_id, secret_hash)
        self.assertTrue(is_valid, f"Failed to validate client credentials. Client ID: {client_id}, Secret Hash: {secret_hash}")

if __name__ == "__main__":
    unittest.main()