import unittest
from apps import api

class TestCircles(unittest.TestCase):

    def setUp(self):
        api.purge()
        api.init_db()

    def test_circle_creation(self):
        data = {
            "name": "Test Circle",
            "description": "A test circle.",
            "tag": "test",
            "parents": {"root": 15}
        }
        resp = api.circles.new(**data)
        self.assertEqual(resp.status, "ok", f"Failed to create circle: {resp.message}, Response data: {resp.data}")

    def test_circle_get_and_update(self):
        data = {
            "name": "Test Circle",
            "description": "A test circle.",
            "tag": "test",
            "parents": {"root": 15}
        }
        circle = api.circles.new(**data).data
        circle_id = circle["id"]

        # Test get
        resp = api.circles.get(circle_id)
        self.assertEqual(resp.status, "ok", f"Failed to get circle: {resp.message}, Response data: {resp.data}")

        # Test update
        update_data = {"name": "Updated Circle", "description": "Updated description"}
        resp = api.circles.update(circle_id, **update_data)
        self.assertEqual(resp.status, "ok", f"Failed to update circle: {resp.message}, Response data: {resp.data}")

    def test_circle_delete(self):
        data = {
            "name": "Test Circle",
            "description": "A test circle.",
            "tag": "test",
            "parents": {"root": 15}
        }
        circle = api.circles.new(**data).data
        circle_id = circle["id"]

        # Test delete
        resp = api.circles.delete(circle_id)
        self.assertEqual(resp.status, "ok", f"Failed to delete circle: {resp.message}, Response data: {resp.data}")

if __name__ == "__main__":
    unittest.main()
