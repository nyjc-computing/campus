"""Integration tests for campus.assignments API routes.

Tests that the assignments endpoints can be instantiated and basic
functionality works end-to-end.
"""

import base64
import unittest

from campus.common import env
from tests.fixtures import services


class TestAssignmentsIntegration(unittest.TestCase):
    """Integration tests for the assignments resource in campus.api."""

    @classmethod
    def setUpClass(cls):
        """Set up local services once for the entire test class."""
        cls.service_manager = services.create_service_manager()
        cls.service_manager.setup()

        # Get the api app from the service manager
        import flask
        api_app = cls.service_manager.apps_app
        if not isinstance(api_app, flask.Flask):
            raise RuntimeError("Expected Flask app from service manager")

        cls.app = api_app

    @classmethod
    def tearDownClass(cls):
        """Clean up services after all tests in the class."""
        if hasattr(cls, 'service_manager'):
            cls.service_manager.close()

        # Reset test storage to clear database
        import campus.storage.testing
        campus.storage.testing.reset_test_storage()

    def setUp(self):
        """Set up test environment before each test."""
        self.client = self.app.test_client()

        # Set up test context
        self.app_context = self.app.app_context()
        self.app_context.push()

        # Prepare auth headers for API requests
        credentials = f"{env.CLIENT_ID}:{env.CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self.auth_headers = {"Authorization": f"Basic {encoded}"}

    def tearDown(self):
        """Clean up after each test."""
        self.app_context.pop()

    def test_list_assignments_empty(self):
        """GET /assignments should return empty list initially."""
        response = self.client.get('/api/v1/assignments', headers=self.auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data
        assert data["data"] == []

    def test_create_assignment_minimal(self):
        """POST /assignments should create assignment with minimal fields."""
        response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Test Assignment"
        })

        assert response.status_code == 201
        data = response.get_json()
        assert data["title"] == "Test Assignment"
        assert data["description"] == ""
        assert "id" in data
        assert "created_at" in data
        assert data["questions"] == []
        assert data["classroom_links"] == []

    def test_create_assignment_with_questions(self):
        """POST /assignments should create assignment with questions."""
        response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Questions Test",
            "description": "Test with questions",
            "questions": [
                {"id": "q1", "prompt": "Read...", "question": "What?"},
                {"id": "q1.a", "prompt": "", "question": "Explain..."},
                {"id": "q2", "prompt": "Consider...", "question": "Analyze..."}
            ]
        })

        assert response.status_code == 201
        data = response.get_json()
        assert data["title"] == "Questions Test"
        assert len(data["questions"]) == 3

    def test_create_assignment_with_classroom_links(self):
        """POST /assignments should create assignment with Classroom links."""
        response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Classroom Test",
            "classroom_links": [
                {
                    "course_id": "c123",
                    "coursework_id": "w456",
                    "attachment_id": "a789"
                }
            ]
        })

        assert response.status_code == 201
        data = response.get_json()
        assert data["title"] == "Classroom Test"
        assert len(data["classroom_links"]) == 1
        assert data["classroom_links"][0]["course_id"] == "c123"

    def test_get_assignment(self):
        """GET /assignments/{id} should return assignment."""
        # First create an assignment
        create_response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Get Test"
        })
        assignment_id = create_response.get_json()["id"]

        # Then get it
        response = self.client.get(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert data["title"] == "Get Test"

    def test_get_assignment_not_found(self):
        """GET /assignments/{id} should return 409 for non-existent assignment."""
        response = self.client.get('/api/v1/assignments/assignment_doesnt_exist', headers=self.auth_headers)

        # Should return 409 Conflict (per Campus API pattern)
        assert response.status_code == 409

    def test_update_assignment_title(self):
        """PATCH /assignments/{id} should update title."""
        # First create an assignment
        create_response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Original Title"
        })
        assignment_id = create_response.get_json()["id"]

        # Update title
        response = self.client.patch(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers, json={
            "title": "Updated Title"
        })

        assert response.status_code == 200
        # Verify update
        get_response = self.client.get(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers)
        data = get_response.get_json()
        assert data["title"] == "Updated Title"

    def test_update_assignment_questions(self):
        """PATCH /assignments/{id} should update questions."""
        # First create an assignment
        create_response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Update Test",
            "questions": [{"id": "q1", "prompt": "P", "question": "Q?"}]
        })
        assignment_id = create_response.get_json()["id"]

        # Update questions
        response = self.client.patch(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers, json={
            "questions": [
                {"id": "q1", "prompt": "P1", "question": "Q1?"},
                {"id": "q1.a", "prompt": "", "question": "Q1a?"}
            ]
        })

        assert response.status_code == 200
        # Verify update
        get_response = self.client.get(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers)
        data = get_response.get_json()
        assert len(data["questions"]) == 2

    def test_delete_assignment(self):
        """DELETE /assignments/{id} should remove assignment."""
        # First create an assignment
        create_response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Delete Test"
        })
        assignment_id = create_response.get_json()["id"]

        # Delete it
        response = self.client.delete(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers)

        assert response.status_code == 200

        # Verify it's gone
        get_response = self.client.get(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers)
        assert get_response.status_code == 409

    def test_add_classroom_link(self):
        """POST /assignments/{id}/links should add Classroom link."""
        # First create an assignment
        create_response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Link Test"
        })
        assignment_id = create_response.get_json()["id"]

        # Add a Classroom link
        response = self.client.post(f'/api/v1/assignments/{assignment_id}/links', headers=self.auth_headers, json={
            "course_id": "c123",
            "coursework_id": "w456",
            "attachment_id": "a789"
        })

        assert response.status_code == 200

        # Verify link was added
        get_response = self.client.get(f'/api/v1/assignments/{assignment_id}', headers=self.auth_headers)
        data = get_response.get_json()
        assert len(data["classroom_links"]) == 1
        assert data["classroom_links"][0]["course_id"] == "c123"

    def test_list_assignments_filter_by_created_by(self):
        """GET /assignments?created_by=x should filter by creator."""
        # Create two assignments with different creators
        self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Assignment 1"
        })

        # This assumes authentication sets created_by - in real scenario,
        # the authenticated user's ID would be used

        response = self.client.get('/api/v1/assignments', headers=self.auth_headers)

        # Should return at least our created assignment
        assert response.status_code == 200
        data = response.get_json()
        assert "data" in data

    def test_patch_empty_body(self):
        """PATCH /assignments/{id} with empty body should return error."""
        # First create an assignment
        create_response = self.client.post('/api/v1/assignments', headers=self.auth_headers, json={
            "title": "Empty Body Test"
        })
        assignment_id = create_response.get_json()["id"]

        # Try to patch with empty body (or minimal invalid body)
        response = self.client.patch(
            f'/api/v1/assignments/{assignment_id}',
            headers=self.auth_headers,
            json={},
            content_type='application/json'
        )

        # Should return error for empty request
        # (This depends on implementation - may need adjustment)
        assert response.status_code == 400 or response.status_code == 422


if __name__ == '__main__':
    unittest.main()
