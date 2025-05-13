import unittest
from apps import palmtree


class TestClientApplications(unittest.TestCase):

    def setUp(self):
        palmtree.purge()
        palmtree.init_db()

    def test_client_application_creation(self):
        data = {
            "owner": "test.owner@example.com",
            "name": "Test Application",
            "description": "A test client application."
        }
        resp = palmtree.clients.applications.new(**data)
        self.assertEqual(resp.status, "ok", f"Failed to create client application: {resp.message}, Response data: {resp.data}")

    def test_client_application_rejection_and_approval(self):
        data = {
            "owner": "test.owner@example.com",
            "name": "Test Application",
            "description": "A test client application."
        }
        resp = palmtree.clients.applications.new(**data)
        application_id = resp.data['id']

        # Test rejection
        resp = palmtree.clients.applications.reject(application_id)
        self.assertEqual(resp.status, "ok", f"Failed to reject client application: {resp.message}, Response data: {resp.data}")

        # Test approval
        resp = palmtree.clients.applications.approve(application_id)
        self.assertEqual(resp.status, "ok", f"Failed to approve client application: {resp.message}, Response data: {resp.data}")

if __name__ == "__main__":
    unittest.main()