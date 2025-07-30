import unittest
from campus.apps.api.routes import admin
from campus.models import client


class TestClients(unittest.TestCase):

    def setUp(self):
        admin.purge_db()
        admin.init_db()

    def test_client_creation(self):
        data = {
            "name": "Test Client",
            "description": "A test client.",
        }
        client_obj = client.Client()
        resp = client_obj.new(**data)
        self.assertIsNotNone(resp)
\
    def test_validating_credentials(self):
        data = {
            "name": "Test Client",
            "description": "A test client.",
        }
        client_obj = client.Client()
        client_data = client_obj.new(**data)
        client_id = client_data["id"]
        result = client_obj.replace(client_id)
        secret_hash = result["secret"]

        # Test credential validation
        is_valid = client_obj.validate_credentials(client_id, secret_hash)
        self.assertTrue(is_valid, f"Failed to validate client credentials. Client ID: {client_id}, Secret Hash: {secret_hash}")

if __name__ == "__main__":
    unittest.main()