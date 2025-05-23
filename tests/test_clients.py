import unittest
from apps import api


class TestClients(unittest.TestCase):

    def setUp(self):
        api.purge()
        api.init_db()

    def test_client_creation(self):
        data = {
            "name": "Test Client",
            "description": "A test client.",
        }
        resp = api.clients.new(**data)
        self.assertEqual(resp.status, "ok", f"Failed to create client: {resp.message}, Response data: {resp.data}")
\
    def test_validating_credentials(self):
        data = {
            "name": "Test Client",
            "description": "A test client.",
        }
        client = api.clients.new(**data).data
        client_id = client["id"]
        result = api.clients.replace(client_id).data
        secret_hash = result["secret"]

        # Test credential validation
        is_valid = api.clients.validate_credentials(client_id, secret_hash)
        self.assertTrue(is_valid, f"Failed to validate client credentials. Client ID: {client_id}, Secret Hash: {secret_hash}")

if __name__ == "__main__":
    unittest.main()