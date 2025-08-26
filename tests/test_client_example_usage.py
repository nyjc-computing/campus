"""Example usage of Flask test client implementations.

This demonstrates how to use the FlaskTestClient and FlaskTestResponse
implementations for testing Campus client code.
"""

from flask import Flask, jsonify
from campus.client.core import Campus
from tests.test_client import create_test_client_factory


def create_test_app():
    """Create a test Flask app with sample routes."""
    app = Flask(__name__)

    @app.route('/users', methods=['POST'])
    def create_user():
        return jsonify({"id": "user3", "name": "Charlie"}), 201

    @app.route('/users/<user_id>', methods=['GET'])
    def get_user(user_id):
        return jsonify({"id": user_id, "name": f"User {user_id}"})

    @app.route('/users/<user_id>/profile', methods=['GET'])
    def get_user_profile(user_id):
        return jsonify({
            "id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com",
            "created_at": "2025-01-01T00:00:00Z"
        })

    @app.route('/admin/status')
    def admin_status():
        return jsonify({"status": "ok", "message": "Admin endpoint is live."})

    return app


def example_usage():
    """Example of using the test implementations."""
    # Create test app and get its test client
    app = create_test_app()
    flask_test_client = app.test_client()

    # Create a client factory for the Campus client
    client_factory = create_test_client_factory(flask_test_client)

    # Create Campus client using the test factory
    campus = Campus(client_factory)

    # Use the Campus client normally - it will use the test Flask app
    # instead of making real HTTP requests

    # Test users endpoint
    print("Testing users.new():")
    response = campus.users.new(email="test@example.com", name="Test User")
    print(f"Status: {response.status}")
    print(f"Data: {response.json()}")

    print("\nTesting users[user_id].get():")
    response = campus.users["test123"].get()
    print(f"Status: {response.status}")
    print(f"Data: {response.json()}")

    print("\nTesting users[user_id].profile():")
    response = campus.users["test123"].profile()
    print(f"Status: {response.status}")
    print(f"Data: {response.json()}")

    print("\nTesting admin.status():")
    response = campus.admin.status()
    print(f"Status: {response.status}")
    print(f"Data: {response.json()}")


if __name__ == '__main__':
    example_usage()
