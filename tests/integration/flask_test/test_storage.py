#!/usr/bin/env python3
"""Test Flask test client strategy with storage backends"""

from tests.flask_test import FlaskTestClient, create_test_app
import campus.auth


def test_auth_with_storage():
    """Test that auth service works with test storage configuration."""
    print("Testing auth service with test storage...")

    # Create auth app using proper factory function
    # This handles ENV, STORAGE_MODE, and test configuration automatically
    app = create_test_app(campus.auth)

    # Debug: Print all registered routes
    print("Registered routes:")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.rule} -> {rule.endpoint}")

    # Test with FlaskTestClient
    with FlaskTestClient(app) as client:
        # Test the test health endpoint we added
        response = client.get("/test/health")
        print(f"Test health endpoint: {response.status_code}")
        print(f"Response: {response.json()}")

        if response.status_code == 200:
            print("✅ Auth service with test storage works! (Health check passed)")
        else:
            print(f"❌ Unexpected status code: {response.status_code}")


if __name__ == "__main__":
    test_auth_with_storage()
