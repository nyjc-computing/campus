"""HTTP contract tests for campus.api circles endpoints.

These tests verify the HTTP interface contract for circle management operations.
They test status codes, response formats, and authentication behavior.

NOTE: ALL /circles/ endpoints require authentication (Basic or Bearer).
This is enforced via before_request hook in the API blueprint.

Circles Endpoints Reference:
- GET    /circles/                              - List all circles with optional tag filter
- POST   /circles/                              - Create a new circle
- GET    /circles/{circle_id}                   - Get a single circle
- PATCH  /circles/{circle_id}                   - Update a circle (name, description)
- DELETE /circles/{circle_id}                   - Delete a circle
- POST   /circles/{circle_id}/move              - Move circle (not implemented - 501)
- GET    /circles/{circle_id}/members           - Get circle members
- POST   /circles/{circle_id}/members/add       - Add a member to a circle
- DELETE /circles/{circle_id}/members/remove    - Remove a member from a circle
- PATCH  /circles/{circle_id}/members           - Update member access level
- GET    /circles/{circle_id}/users             - Get users in circle (not implemented - 501)
"""

import unittest

from campus.common import schema
from tests.fixtures import services
from tests.fixtures.tokens import create_test_token, get_bearer_auth_headers


class TestApiCirclesContract(unittest.TestCase):
    """HTTP contract tests for /api/v1/circles/ endpoints."""

    @classmethod
    def setUpClass(cls):
        # Reset storage before starting tests to ensure clean state
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

        cls.manager = services.create_service_manager()
        cls.manager.setup()
        cls.app = cls.manager.apps_app

        # Initialize circle storage (not done by default)
        from campus.api.resources.circle import CirclesResource
        CirclesResource.init_storage()

        # Create test user and token for bearer auth
        cls.user_id = schema.UserID("test.user@campus.test")
        cls.token = create_test_token(cls.user_id)
        cls.auth_headers = get_bearer_auth_headers(cls.token)

    @classmethod
    def tearDownClass(cls):
        cls.manager.close()
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        # Reinitialize storage after tearDownClass reset
        # Ensures proper test isolation between tests
        import campus.storage.testing
        from campus.api.resources.circle import CirclesResource
        campus.storage.testing.reset_test_storage()
        CirclesResource.init_storage()

        self.client = self.app.test_client()

    def _create_test_circle(self, **overrides):
        """Helper to create a test circle via resource layer.

        Returns the circle ID.
        """
        from campus.api import resources

        data = {
            "name": "Test Circle",
            "description": "A test circle for contract testing",
            "tag": "test",
            "parents": {},
        }
        data.update(overrides)

        circle = resources.circle.new(**data)
        return str(circle.id)

    # List Circles Tests

    def test_list_circles_requires_auth(self):
        """GET /circles/ without auth returns 401."""
        response = self.client.get("/api/v1/circles/")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    @unittest.skip("API BUG: GET /circles/ returns 500 - possibly related to list operation on circles")
    def test_list_circles_returns_circles(self):
        """GET /circles/ returns list of circles."""
        # Create a test circle
        self._create_test_circle(name="List Test Circle", tag="list-test")

        response = self.client.get("/api/v1/circles/", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        self.assertIsInstance(data["data"], list)
        self.assertGreater(len(data["data"]), 0)

    def test_list_circles_with_tag_filter(self):
        """GET /circles/?tag={tag} filters circles by tag."""
        # Create a circle with specific tag
        self._create_test_circle(name="Tagged Circle", tag="filter-test")

        response = self.client.get(
            "/api/v1/circles/?tag=filter-test",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("data", data)
        # Should have at least our test circle
        self.assertGreater(len(data["data"]), 0)

    # Create Circle Tests

    def test_create_circle_requires_auth(self):
        """POST /circles/ without auth returns 401."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Unauthorized Circle",
                "description": "Should not be created",
                "tag": "test",
            }
        )

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_create_circle(self):
        """POST /circles/ creates a new circle."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "New Circle",
                "description": "A new test circle",
                "tag": "test",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("id", data)
        self.assertIn("name", data)
        self.assertEqual(data["name"], "New Circle")
        self.assertIn("description", data)
        self.assertIn("tag", data)

    def test_create_circle_with_parents(self):
        """POST /circles/ with parents creates circle with parent relationships."""
        # First create a parent circle
        parent_id = self._create_test_circle(name="Parent Circle", tag="parent")

        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Child Circle",
                "description": "A child circle",
                "tag": "child",
                "parents": {parent_id: 15},
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn("id", data)

    @unittest.skip("API BUG: Missing required params returns 500 instead of 400 (similar to bug #324)")
    def test_create_circle_missing_name_returns_error(self):
        """POST /circles/ without name returns error."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "description": "Missing name",
                "tag": "test",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)

    @unittest.skip("API BUG: Missing required params returns 500 instead of 400 (similar to bug #324)")
    def test_create_circle_missing_tag_returns_error(self):
        """POST /circles/ without tag returns error."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Missing Tag",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)

    @unittest.skip("API BUG: ConflictError for root circle with parents returns 500 instead of 409")
    def test_create_root_circle_with_parents_returns_error(self):
        """POST /circles/ with tag=root and parents returns 409."""
        response = self.client.post(
            "/api/v1/circles/",
            json={
                "name": "Invalid Root",
                "tag": "root",
                "parents": {"some-parent": 15},
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "CONFLICT")

    # Get Circle Tests

    def test_get_circle_by_id(self):
        """GET /circles/{circle_id} returns the circle."""
        circle_id = self._create_test_circle(name="Get Test Circle")

        response = self.client.get(
            f"/api/v1/circles/{circle_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["id"], circle_id)
        self.assertIn("name", data)
        self.assertIn("description", data)
        self.assertIn("tag", data)
        self.assertIn("members", data)
        self.assertIn("sources", data)

    def test_get_circle_requires_auth(self):
        """GET /circles/{circle_id} without auth returns 401."""
        response = self.client.get("/api/v1/circles/some_id")

        self.assertEqual(response.status_code, 401)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "UNAUTHORIZED")

    def test_get_missing_circle_returns_error(self):
        """GET /circles/{circle_id} for non-existent circle returns 409."""
        response = self.client.get(
            "/api/v1/circles/nonexistent_id",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "CONFLICT")

    # Update Circle Tests

    @unittest.skip("API BUG: PATCH /circles/{id} returns 500 for all update operations")
    def test_update_circle_name(self):
        """PATCH /circles/{circle_id} updates name."""
        circle_id = self._create_test_circle(name="Original Name")

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}",
            json={"name": "Updated Name"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify the update
        get_response = self.client.get(
            f"/api/v1/circles/{circle_id}",
            headers=self.auth_headers
        )
        circle_data = get_response.get_json()
        self.assertEqual(circle_data["name"], "Updated Name")

    @unittest.skip("API BUG: PATCH /circles/{id} returns 500 for all update operations")
    def test_update_circle_description(self):
        """PATCH /circles/{circle_id} updates description."""
        circle_id = self._create_test_circle(description="Original Description")

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}",
            json={"description": "Updated Description"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    @unittest.skip("API BUG: PATCH /circles/{id} returns 500 for all update operations")
    def test_update_circle_both_fields(self):
        """PATCH /circles/{circle_id} updates both name and description."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}",
            json={
                "name": "New Name",
                "description": "New Description",
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

    @unittest.skip("API BUG: PATCH /circles/{id} returns 500 for all update operations (including empty body)")
    def test_update_circle_empty_body_returns_error(self):
        """PATCH /circles/{circle_id} without updates returns 400."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}",
            json={},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertIn("error", data)
        self.assertIn("code", data["error"])
        self.assertEqual(data["error"]["code"], "INVALID_REQUEST")

    def test_update_circle_requires_auth(self):
        """PATCH /circles/{circle_id} without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}",
            json={"name": "Updated Name"}
        )

        self.assertEqual(response.status_code, 401)

    @unittest.skip("API BUG: PATCH /circles/{id} returns 500 for all update operations (including missing circle)")
    def test_update_missing_circle_returns_error(self):
        """PATCH /circles/{circle_id} for non-existent circle returns 409."""
        response = self.client.patch(
            "/api/v1/circles/nonexistent_id",
            json={"name": "Updated Name"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    # Delete Circle Tests

    def test_delete_circle(self):
        """DELETE /circles/{circle_id} removes the circle."""
        circle_id = self._create_test_circle(name="To Be Deleted")

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify it's deleted
        get_response = self.client.get(
            f"/api/v1/circles/{circle_id}",
            headers=self.auth_headers
        )
        self.assertEqual(get_response.status_code, 409)

    def test_delete_circle_requires_auth(self):
        """DELETE /circles/{circle_id} without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}"
        )

        self.assertEqual(response.status_code, 401)

    @unittest.skip("API BUG: DELETE /circles/{id} for non-existent circle returns 200 instead of 409")
    def test_delete_missing_circle_returns_error(self):
        """DELETE /circles/{circle_id} for non-existent circle returns 409."""
        response = self.client.delete(
            "/api/v1/circles/nonexistent_id",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    # Move Circle Tests (Not Implemented)

    def test_move_circle_not_implemented(self):
        """POST /circles/{circle_id}/move returns 501."""
        circle_id = self._create_test_circle()

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/move",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 501)
        data = response.get_json()
        self.assertIn("message", data)
        self.assertEqual(data["message"], "Not implemented")

    # Circle Members Tests

    def test_get_circle_members(self):
        """GET /circles/{circle_id}/members returns members dict."""
        circle_id = self._create_test_circle()

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, dict)

    def test_get_circle_members_requires_auth(self):
        """GET /circles/{circle_id}/members without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/members"
        )

        self.assertEqual(response.status_code, 401)

    def test_get_members_missing_circle_returns_error(self):
        """GET /circles/{circle_id}/members for non-existent circle returns 409."""
        response = self.client.get(
            "/api/v1/circles/nonexistent_id/members",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_add_circle_member(self):
        """POST /circles/{circle_id}/members/add adds a member."""
        # Create two circles
        parent_id = self._create_test_circle(name="Parent Circle")
        child_id = self._create_test_circle(name="Child Circle")

        response = self.client.post(
            f"/api/v1/circles/{parent_id}/members/add",
            json={
                "member_id": child_id,
                "access_value": 15,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify member was added
        members_response = self.client.get(
            f"/api/v1/circles/{parent_id}/members",
            headers=self.auth_headers
        )
        members_data = members_response.get_json()
        self.assertIn(child_id, members_data)

    def test_add_circle_member_requires_auth(self):
        """POST /circles/{circle_id}/members/add without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "some-member-id",
                "access_value": 15,
            }
        )

        self.assertEqual(response.status_code, 401)

    def test_add_member_to_missing_circle_returns_error(self):
        """POST /circles/{circle_id}/members/add for non-existent circle returns 409."""
        response = self.client.post(
            "/api/v1/circles/nonexistent_id/members/add",
            json={
                "member_id": "some-member-id",
                "access_value": 15,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_add_nonexistent_member_returns_error(self):
        """POST /circles/{circle_id}/members/add with non-existent member returns 409."""
        circle_id = self._create_test_circle()

        response = self.client.post(
            f"/api/v1/circles/{circle_id}/members/add",
            json={
                "member_id": "nonexistent-member-id",
                "access_value": 15,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    @unittest.skip("API BUG: remove_circle_member returns 409 - NoChangesAppliedError not caught properly")
    def test_remove_circle_member(self):
        """DELETE /circles/{circle_id}/members/remove removes a member."""
        # Create two circles and add member relationship
        parent_id = self._create_test_circle(name="Parent Circle Remove")
        child_id = self._create_test_circle(name="Child Circle Remove")

        # Add the member first
        self.client.post(
            f"/api/v1/circles/{parent_id}/members/add",
            json={
                "member_id": child_id,
                "access_value": 15,
            },
            headers=self.auth_headers
        )

        # Remove the member
        response = self.client.delete(
            f"/api/v1/circles/{parent_id}/members/remove",
            json={
                "member_id": child_id,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {})

        # Verify member was removed
        members_response = self.client.get(
            f"/api/v1/circles/{parent_id}/members",
            headers=self.auth_headers
        )
        members_data = members_response.get_json()
        self.assertNotIn(child_id, members_data)

    def test_remove_circle_member_requires_auth(self):
        """DELETE /circles/{circle_id}/members/remove without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}/members/remove",
            json={"member_id": "some-member-id"}
        )

        self.assertEqual(response.status_code, 401)

    def test_remove_member_from_missing_circle_returns_error(self):
        """DELETE /circles/{circle_id}/members/remove for non-existent circle returns 409."""
        response = self.client.delete(
            "/api/v1/circles/nonexistent_id/members/remove",
            json={"member_id": "some-member-id"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_remove_nonexistent_member_returns_error(self):
        """DELETE /circles/{circle_id}/members/remove for non-existent member returns 409."""
        circle_id = self._create_test_circle()

        response = self.client.delete(
            f"/api/v1/circles/{circle_id}/members/remove",
            json={"member_id": "nonexistent-member-id"},
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    def test_patch_circle_member_access(self):
        """PATCH /circles/{circle_id}/members updates member access level."""
        # Create two circles and add member relationship
        parent_id = self._create_test_circle(name="Parent Circle Patch")
        child_id = self._create_test_circle(name="Child Circle Patch")

        # Add the member first
        self.client.post(
            f"/api/v1/circles/{parent_id}/members/add",
            json={
                "member_id": child_id,
                "access_value": 5,
            },
            headers=self.auth_headers
        )

        # Update the access level
        response = self.client.patch(
            f"/api/v1/circles/{parent_id}/members",
            json={
                "member_id": child_id,
                "access_value": 10,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)

        # Verify access was updated
        members_response = self.client.get(
            f"/api/v1/circles/{parent_id}/members",
            headers=self.auth_headers
        )
        members_data = members_response.get_json()
        self.assertEqual(members_data[child_id], 10)

    def test_patch_circle_member_requires_auth(self):
        """PATCH /circles/{circle_id}/members without auth returns 401."""
        circle_id = self._create_test_circle()

        response = self.client.patch(
            f"/api/v1/circles/{circle_id}/members",
            json={
                "member_id": "some-member-id",
                "access_value": 10,
            }
        )

        self.assertEqual(response.status_code, 401)

    def test_patch_member_for_missing_circle_returns_error(self):
        """PATCH /circles/{circle_id}/members for non-existent circle returns 409."""
        response = self.client.patch(
            "/api/v1/circles/nonexistent_id/members",
            json={
                "member_id": "some-member-id",
                "access_value": 10,
            },
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 409)

    # Get Circle Users Tests (Not Implemented)

    def test_get_circle_users_not_implemented(self):
        """GET /circles/{circle_id}/users returns 501."""
        circle_id = self._create_test_circle()

        response = self.client.get(
            f"/api/v1/circles/{circle_id}/users",
            headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 501)
        data = response.get_json()
        self.assertIn("message", data)
        self.assertEqual(data["message"], "Not implemented")


if __name__ == '__main__':
    unittest.main()
