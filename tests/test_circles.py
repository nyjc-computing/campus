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

    def test_circle_members(self):
        # Create two circles: parent and member
        parent_data = {
            "name": "Parent Circle",
            "description": "Parent circle.",
            "tag": "parent",
            "parents": {"root": 15}
        }
        member_data = {
            "name": "Member Circle",
            "description": "Member circle.",
            "tag": "member",
            "parents": {"root": 15}
        }
        parent = api.circles.new(**parent_data).data
        member = api.circles.new(**member_data).data
        parent_id = parent["id"]
        member_id = member["id"]

        # Add member to parent
        add_resp = api.circles.members.add(parent_id, member_id=member_id, access_value=1)
        self.assertEqual(add_resp.status, "ok", f"Failed to add member: {add_resp.message}")

        # List members
        list_resp = api.circles.members.list(parent_id)
        self.assertEqual(list_resp.status, "ok", f"Failed to list members: {list_resp.message}")
        # list_resp.data is a dict of member_id -> access_value
        self.assertIn(member_id, list_resp.data)

        # Update member access
        patch_resp = api.circles.members.set(parent_id, member_id=member_id, access_value=2)
        self.assertEqual(patch_resp.status, "ok", f"Failed to update member: {patch_resp.message}")
        # Optionally, check access value updated
        updated_members = api.circles.members.list(parent_id).data
        self.assertIn(member_id, updated_members)
        self.assertEqual(updated_members[member_id], 2)

        # Remove member
        remove_resp = api.circles.members.remove(parent_id, member_id=member_id)
        self.assertEqual(remove_resp.status, "ok", f"Failed to remove member: {remove_resp.message}")
        # Confirm removal
        list_after_remove = api.circles.members.list(parent_id).data
        self.assertNotIn(member_id, list_after_remove)

if __name__ == "__main__":
    unittest.main()
