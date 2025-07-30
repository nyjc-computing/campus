import unittest
from campus.apps.api.routes import admin
from campus.models import circle


class TestCircles(unittest.TestCase):

    def setUp(self):
        admin.purge_db()
        admin.init_db()

    def test_circle_creation(self):
        data = {
            "name": "Test Circle",
            "description": "A test circle.",
            "tag": "test",
            "parents": {"root": 15}
        }
        circle_obj = circle.Circle()
        resp = circle_obj.new(**data)
        self.assertIsNotNone(resp)

    def test_circle_get_and_update(self):
        data = {
            "name": "Test Circle",
            "description": "A test circle.",
            "tag": "test",
            "parents": {"root": 15}
        }
        circle_obj = circle.Circle()
        circle_data = circle_obj.new(**data)
        circle_id = circle_data["id"]

        # Test get
        resp = circle_obj.get(circle_id)
        self.assertIsNotNone(resp)

        # Test update
        update_data = {"name": "Updated Circle", "description": "Updated description"}
        circle_obj.update(circle_id, **update_data)

    def test_circle_delete(self):
        data = {
            "name": "Test Circle",
            "description": "A test circle.",
            "tag": "test",
            "parents": {"root": 15}
        }
        circle_obj = circle.Circle()
        circle_data = circle_obj.new(**data)
        circle_id = circle_data["id"]

        # Test delete
        circle_obj.delete(circle_id)

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
        circle_obj = circle.Circle()
        parent = circle_obj.new(**parent_data)
        member = circle_obj.new(**member_data)
        parent_id = parent["id"]
        member_id = member["id"]

        # Add member to parent
        circle_obj.members.add(parent_id, member_id=member_id, access_value=1)

        # List members
        members = circle_obj.members.list(parent_id)
        self.assertIn(member_id, members)

        # Update member access
        circle_obj.members.set(parent_id, member_id=member_id, access_value=2)
        updated_members = circle_obj.members.list(parent_id)
        self.assertIn(member_id, updated_members)
        self.assertEqual(updated_members[member_id], 2)

        # Remove member
        circle_obj.members.remove(parent_id, member_id=member_id)
        list_after_remove = circle_obj.members.list(parent_id)
        self.assertNotIn(member_id, list_after_remove)


if __name__ == "__main__":
    unittest.main()
